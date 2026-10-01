"""
Blueprint analytics and resource cost engine.
"""

from __future__ import annotations

import csv
import json
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Set

import safe_xml
from mappings.dlc_substitution import DLC_TO_BASE_PAIRS
from resource_paths import resource_path


SEVERITY_INFO = "Info"
SEVERITY_WARNING = "Warning"
SEVERITY_ERROR = "Error"

DLC_KEYWORDS = (
    "scifi",
    "industrial",
    "wasteland",
    "warfare",
    "reskin",
    "decorative",
    "desert",
    "cab",
    "buggy",
    "sparks",
    "vending",
    "storeblock",
)
MECHANICAL_KEYWORDS = ("rotor", "stator", "hinge", "piston")


@dataclass
class HealthIssue:
    severity: str
    code: str
    message: str
    suggestion: str
    fix_id: Optional[str] = None


@dataclass
class BlueprintAnalyticsResult:
    blueprint_name: str
    block_count: int
    block_counts: Dict[str, int]
    category_counts: Dict[str, int]
    unknown_subtypes: List[str]
    component_totals: Dict[str, int]
    ingot_totals: Dict[str, float]
    ore_totals: Dict[str, float]
    pcu_total: int
    mass_total: float
    grid_size: str
    health_issues: List[HealthIssue] = field(default_factory=list)


@dataclass
class SE2Readiness:
    dlc_count: int
    script_count: int
    subgrid_count: int
    score: int
    status: str
    dlc_subtypes: tuple[str, ...] = ()
    connector_count: int = 0


# Player-facing labels. OPTIMAL is a low-risk estimate, not a load guarantee.
SE2_STATUS_TITLES = {
    "OPTIMAL": "Straightforward ship",
    "STABLE": "Mostly straightforward",
    "COMPLEX": "Needs cleanup",
    "FRAGILE": "Hard to carry over",
}

SE2_PLANNING_BLURB = (
    "This score is a planning estimate from DLC blocks, scripts, and mechanical subgrids. "
    "It does not mean the ship will load in Space Engineers 2."
)


@dataclass
class ConversionComparison:
    mode: str
    block_changes: Dict[str, int]
    before_components: Dict[str, int]
    after_components: Dict[str, int]
    component_delta: Dict[str, int]
    before_ingots: Dict[str, float]
    after_ingots: Dict[str, float]
    ingot_delta: Dict[str, float]
    before_ores: Dict[str, float]
    after_ores: Dict[str, float]
    ore_delta: Dict[str, float]
    before_pcu: int
    after_pcu: int
    pcu_delta: int
    before_mass: float
    after_mass: float
    mass_delta: float


class BlockCostDatabase:
    """Loads block/component/ore conversion data from JSON."""

    def __init__(self, file_path: Path):
        self.file_path = Path(file_path)
        self.metadata: Dict = {}
        self.component_to_ingot: Dict[str, Dict[str, float]] = {}
        self.ore_yields: Dict[str, float] = {}
        self.blocks: Dict[str, Dict] = {}
        if not self.file_path.exists():
            return
        with open(self.file_path, "r", encoding="utf-8") as handle:
            data = json.load(handle)

        self.metadata = data.get("metadata", {})
        self.component_to_ingot = data.get("component_to_ingot", {})
        self.ore_yields = data.get("ore_yields", {})
        self.blocks = data.get("blocks", {})

    def get_block(self, subtype: str) -> Optional[Dict]:
        if subtype in self.blocks:
            return self.blocks[subtype]
        return self._infer_cost(subtype)

    def known_block_ids(self) -> List[str]:
        return sorted(self.blocks.keys())

    def category_for_subtype(self, subtype: str) -> str:
        block = self.get_block(subtype)
        if block:
            return block.get("category", "utility")

        lowered = subtype.lower()
        if "armor" in lowered:
            return "armor"
        if "thrust" in lowered:
            return "thrusters"
        if "turret" in lowered or "gatling" in lowered or "artillery" in lowered:
            return "weapons"
        return "utility"

    def component_to_ingot_totals(self, components: Dict[str, int]) -> Dict[str, float]:
        ingots: Dict[str, float] = defaultdict(float)
        for component, qty in components.items():
            conversion = self.component_to_ingot.get(component)
            if not conversion:
                continue
            for ingot, per_component in conversion.items():
                ingots[ingot] += qty * float(per_component)
        return dict(ingots)

    def ingot_to_ore_totals(self, ingots: Dict[str, float]) -> Dict[str, float]:
        ores: Dict[str, float] = defaultdict(float)
        for ingot, qty in ingots.items():
            yield_per_ore = self.ore_yields.get(ingot)
            if not yield_per_ore:
                continue
            ores[f"{ingot} Ore"] += qty / float(yield_per_ore)
        return dict(ores)

    def _infer_cost(self, subtype: str) -> Optional[Dict]:
        """
        Cost fallback for unknown armor variants and common blocks.
        """
        lowered = subtype.lower()
        if "armor" in lowered:
            if "heavy" in lowered:
                steel = 150 if subtype.startswith("Large") else 5
                pcu = 1 if subtype.startswith("Large") else 0
                mass = 15100.0 if subtype.startswith("Large") else 30.0
            else:
                steel = 25 if subtype.startswith("Large") else 1
                pcu = 1 if subtype.startswith("Large") else 0
                mass = 2520.0 if subtype.startswith("Large") else 10.0
            return {
                "category": "armor",
                "pcu": pcu,
                "mass": mass,
                "components": {"SteelPlate": steel},
            }
        if "thrust" in lowered:
            return {
                "category": "thrusters",
                "pcu": 10,
                "mass": 1500.0,
                "components": {
                    "SteelPlate": 40,
                    "Construction": 20,
                    "Motor": 20,
                    "Thrust": 10,
                },
            }
        if "reactor" in lowered or "generator" in lowered:
            return {
                "category": "power",
                "pcu": 25,
                "mass": 2000.0,
                "components": {
                    "SteelPlate": 40,
                    "Construction": 20,
                    "Reactor": 10,
                },
            }
        return None


class BlueprintAnalyticsEngine:
    """Performs analytics, health audits, and conversion cost comparisons."""

    def __init__(self, cost_db_path: Optional[Path] = None):
        self.db = BlockCostDatabase(cost_db_path or resource_path("data", "block_costs.json"))

    def analyze_blueprint(self, blueprint_file: Path) -> BlueprintAnalyticsResult:
        tree = safe_xml.parse(blueprint_file)
        return self.analyze_root(
            tree.getroot(),
            blueprint_name=Path(blueprint_file).parent.name,
        )

    def analyze_root(self, root: ET.Element, *, blueprint_name: str) -> BlueprintAnalyticsResult:
        grid_size = self._detect_grid_size(root)

        blocks = root.findall(".//CubeBlocks/MyObjectBuilder_CubeBlock")
        subtype_counts: Dict[str, int] = Counter()
        component_totals: Dict[str, int] = defaultdict(int)
        category_totals: Dict[str, int] = defaultdict(int)
        unknown_subtypes: Set[str] = set()
        pcu_total = 0
        mass_total = 0.0

        for block in blocks:
            subtype = self._get_block_subtype(block)
            if not subtype:
                continue
            subtype_counts[subtype] += 1

            block_cost = self.db.get_block(subtype)
            if not block_cost:
                unknown_subtypes.add(subtype)
                category_totals["unknown"] += 1
                continue

            category = block_cost.get("category", "utility")
            category_totals[category] += 1
            pcu_total += int(block_cost.get("pcu", 0))
            mass_total += float(block_cost.get("mass", 0.0))
            for component, qty in block_cost.get("components", {}).items():
                component_totals[component] += int(qty)

        ingot_totals = self.db.component_to_ingot_totals(component_totals)
        ore_totals = self.db.ingot_to_ore_totals(ingot_totals)
        issues = self._run_health_audit(root, subtype_counts, sorted(unknown_subtypes))

        return BlueprintAnalyticsResult(
            blueprint_name=blueprint_name,
            block_count=sum(subtype_counts.values()),
            block_counts=dict(sorted(subtype_counts.items())),
            category_counts=dict(sorted(category_totals.items())),
            unknown_subtypes=sorted(unknown_subtypes),
            component_totals=dict(sorted(component_totals.items())),
            ingot_totals=dict(sorted(ingot_totals.items())),
            ore_totals=dict(sorted(ore_totals.items())),
            pcu_total=pcu_total,
            mass_total=round(mass_total, 2),
            grid_size=grid_size,
            health_issues=issues,
        )

    def compare_conversion_cost(
        self,
        blueprint_file: Path,
        mapping: Dict[str, str],
        mode: str,
    ) -> ConversionComparison:
        return self.compare_conversion_cost_from_result(
            self.analyze_blueprint(blueprint_file),
            mapping,
            mode,
        )

    def compare_conversion_cost_from_result(
        self,
        result: BlueprintAnalyticsResult,
        mapping: Dict[str, str],
        mode: str,
    ) -> ConversionComparison:
        after_components: Dict[str, int] = defaultdict(int)
        after_pcu = 0
        after_mass = 0.0
        block_changes: Dict[str, int] = {}

        for subtype, count in result.block_counts.items():
            target_subtype = mapping.get(subtype, subtype)
            if target_subtype != subtype:
                block_changes[f"{subtype} -> {target_subtype}"] = count

            block_cost = self.db.get_block(target_subtype)
            if not block_cost:
                continue
            after_pcu += int(block_cost.get("pcu", 0)) * count
            after_mass += float(block_cost.get("mass", 0.0)) * count
            for component, qty in block_cost.get("components", {}).items():
                after_components[component] += int(qty) * count

        before_components = result.component_totals
        before_ingots = result.ingot_totals
        before_ores = result.ore_totals

        after_ingots = self.db.component_to_ingot_totals(after_components)
        after_ores = self.db.ingot_to_ore_totals(after_ingots)

        component_delta = self._int_delta(before_components, after_components)
        ingot_delta = self._numeric_delta(before_ingots, after_ingots)
        ore_delta = self._numeric_delta(before_ores, after_ores)

        return ConversionComparison(
            mode=mode,
            block_changes=dict(sorted(block_changes.items())),
            before_components=dict(sorted(before_components.items())),
            after_components=dict(sorted(after_components.items())),
            component_delta=dict(sorted(component_delta.items())),
            before_ingots=dict(sorted(before_ingots.items())),
            after_ingots=dict(sorted(after_ingots.items())),
            ingot_delta=dict(sorted(ingot_delta.items())),
            before_ores=dict(sorted(before_ores.items())),
            after_ores=dict(sorted(after_ores.items())),
            ore_delta=dict(sorted(ore_delta.items())),
            before_pcu=result.pcu_total,
            after_pcu=after_pcu,
            pcu_delta=after_pcu - result.pcu_total,
            before_mass=result.mass_total,
            after_mass=round(after_mass, 2),
            mass_delta=round(after_mass - result.mass_total, 2),
        )

    @staticmethod
    def export_comparison_csv(comparison: ConversionComparison, destination: Path) -> Path:
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with open(destination, "w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["Metric", "Before", "After", "Delta"])
            writer.writerow(["PCU", comparison.before_pcu, comparison.after_pcu, comparison.pcu_delta])
            writer.writerow(["Mass", comparison.before_mass, comparison.after_mass, comparison.mass_delta])
            writer.writerow([])
            writer.writerow(["Component", "Before", "After", "Delta"])
            for key in sorted(set(comparison.before_components) | set(comparison.after_components)):
                writer.writerow(
                    [
                        key,
                        comparison.before_components.get(key, 0),
                        comparison.after_components.get(key, 0),
                        comparison.component_delta.get(key, 0),
                    ]
                )
            writer.writerow([])
            writer.writerow(["Ingot", "Before", "After", "Delta"])
            for key in sorted(set(comparison.before_ingots) | set(comparison.after_ingots)):
                writer.writerow(
                    [
                        key,
                        round(comparison.before_ingots.get(key, 0.0), 3),
                        round(comparison.after_ingots.get(key, 0.0), 3),
                        round(comparison.ingot_delta.get(key, 0.0), 3),
                    ]
                )
            writer.writerow([])
            writer.writerow(["Ore", "Before", "After", "Delta"])
            for key in sorted(set(comparison.before_ores) | set(comparison.after_ores)):
                writer.writerow(
                    [
                        key,
                        round(comparison.before_ores.get(key, 0.0), 3),
                        round(comparison.after_ores.get(key, 0.0), 3),
                        round(comparison.ore_delta.get(key, 0.0), 3),
                    ]
                )
        return destination

    @staticmethod
    def export_comparison_text(comparison: ConversionComparison, destination: Path) -> Path:
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        lines: List[str] = []
        lines.append(f"Mode: {comparison.mode}")
        lines.append(f"PCU: {comparison.before_pcu} -> {comparison.after_pcu} (delta {comparison.pcu_delta:+d})")
        lines.append(
            f"Mass: {comparison.before_mass:.2f} -> {comparison.after_mass:.2f} "
            f"(delta {comparison.mass_delta:+.2f})"
        )
        lines.append("")
        lines.append("Block changes:")
        for change, count in comparison.block_changes.items():
            lines.append(f"  {change} (x{count})")
        lines.append("")
        lines.append("Component deltas:")
        for component, component_delta_value in sorted(comparison.component_delta.items()):
            lines.append(f"  {component}: {component_delta_value:+d}")
        lines.append("")
        lines.append("Ingot deltas:")
        for ingot, ingot_delta_value in sorted(comparison.ingot_delta.items()):
            lines.append(f"  {ingot}: {ingot_delta_value:+.3f}")
        lines.append("")
        lines.append("Ore deltas:")
        for ore, ore_delta_value in sorted(comparison.ore_delta.items()):
            lines.append(f"  {ore}: {ore_delta_value:+.3f}")

        with open(destination, "w", encoding="utf-8") as handle:
            handle.write("\n".join(lines))
        return destination

    def apply_fix(self, blueprint_file: Path, fix_id: str) -> bool:
        tree = safe_xml.parse(blueprint_file)
        root = tree.getroot()
        cube_blocks = root.find(".//CubeBlocks")
        if cube_blocks is None:
            return False

        grid_size = self._detect_grid_size(root)

        if fix_id == "add_control_block":
            subtype = "LargeBlockCockpit" if grid_size == "Large" else "SmallBlockCockpit"
            block_type = "MyObjectBuilder_Cockpit"
        elif fix_id == "add_power_block":
            subtype = "LargeBlockBatteryBlock" if grid_size == "Large" else "SmallBlockBatteryBlock"
            block_type = "MyObjectBuilder_BatteryBlock"
        else:
            return False

        new_block = ET.SubElement(cube_blocks, "MyObjectBuilder_CubeBlock")
        new_block.set("{http://www.w3.org/2001/XMLSchema-instance}type", block_type)
        ET.SubElement(new_block, "SubtypeName").text = subtype
        ET.SubElement(new_block, "Min").attrib.update({"x": "0", "y": "0", "z": "0"})
        ET.SubElement(new_block, "BlockOrientation").attrib.update(
            {"Forward": "Forward", "Up": "Up"}
        )
        safe_xml.safe_write(tree, blueprint_file)
        return True

    @staticmethod
    def _get_block_subtype(block: ET.Element) -> Optional[str]:
        subtype_name = block.find("SubtypeName")
        if subtype_name is not None and subtype_name.text:
            return subtype_name.text.strip()
        subtype_id = block.find("SubtypeId")
        if subtype_id is not None and subtype_id.text:
            return subtype_id.text.strip()
        return None

    @staticmethod
    def _detect_grid_size(root: ET.Element) -> str:
        element = root.find(".//CubeGrid/GridSizeEnum")
        if element is not None and element.text:
            return element.text.strip()
        return "Unknown"

    @staticmethod
    def _numeric_delta(before: Mapping[str, float], after: Mapping[str, float]) -> Dict[str, float]:
        keys = set(before.keys()) | set(after.keys())
        return {key: after.get(key, 0) - before.get(key, 0) for key in keys}

    @staticmethod
    def _int_delta(before: Mapping[str, int], after: Mapping[str, int]) -> Dict[str, int]:
        keys = set(before.keys()) | set(after.keys())
        return {key: int(after.get(key, 0) - before.get(key, 0)) for key in keys}

    def _run_health_audit(
        self,
        root: ET.Element,
        subtype_counts: Dict[str, int],
        unknown_subtypes: List[str],
    ) -> List[HealthIssue]:
        issues: List[HealthIssue] = []
        subtype_keys = list(subtype_counts.keys())
        lowered = [s.lower() for s in subtype_keys]

        has_control = any(
            key for key in lowered if "cockpit" in key or "controlseat" in key or "remotecontrol" in key
        )
        has_power = any(
            key
            for key in lowered
            if "battery" in key
            or "reactor" in key
            or "hydrogenengine" in key
            or "solar" in key
            or "wind" in key
        )
        if not has_control:
            issues.append(
                HealthIssue(
                    severity=SEVERITY_ERROR,
                    code="missing_control",
                    message="No control block detected (Cockpit/Control Seat/Remote Control).",
                    suggestion="Add a cockpit or remote control to make the grid pilotable.",
                    fix_id="add_control_block",
                )
            )
        if not has_power:
            issues.append(
                HealthIssue(
                    severity=SEVERITY_ERROR,
                    code="missing_power",
                    message="No power source detected (Battery/Reactor/Hydrogen/Solar/Wind).",
                    suggestion="Add a battery or reactor so functional blocks can run.",
                    fix_id="add_power_block",
                )
            )

        thruster_balance = self._thruster_balance(root)
        if thruster_balance:
            issues.append(
                HealthIssue(
                    severity=SEVERITY_WARNING,
                    code="thruster_imbalance",
                    message=thruster_balance,
                    suggestion="Try balancing thrust directions for safer handling.",
                )
            )

        if unknown_subtypes:
            issues.append(
                HealthIssue(
                    severity=SEVERITY_INFO,
                    code="unknown_blocks",
                    message=f"{len(unknown_subtypes)} block subtype(s) are unknown to the local cost database.",
                    suggestion=(
                        "Convert only rewrites subtypes in the checked categories. "
                        "Unknown subtypes are left unchanged. A missing cost entry is not proof the block is vanilla."
                    ),
                )
            )

        return issues

    def _thruster_balance(self, root: ET.Element) -> Optional[str]:
        directions: Counter[str] = Counter()
        thruster_blocks = 0
        for block in root.findall(".//CubeGrid/CubeBlocks/MyObjectBuilder_CubeBlock"):
            subtype = self._get_block_subtype(block)
            if not subtype:
                continue
            if "thrust" not in subtype.lower():
                continue
            thruster_blocks += 1
            orientation = block.find("BlockOrientation")
            if orientation is None:
                continue
            forward = orientation.attrib.get("Forward")
            if forward:
                directions[forward] += 1

        if thruster_blocks < 6:
            return None

        missing = [direction for direction in ("Forward", "Backward", "Up", "Down", "Left", "Right") if directions[direction] == 0]
        if missing:
            return f"Thrusters are missing in direction(s): {', '.join(missing)}."

        counts = [directions[d] for d in ("Forward", "Backward", "Up", "Down", "Left", "Right")]
        if min(counts) == 0:
            return None
        if max(counts) / min(counts) >= 2.5:
            return "Thruster distribution appears heavily unbalanced across directions."
        return None


def _is_dlc_subtype(subtype: str) -> bool:
    """True for a DLC substitution source, or a name that still matches a DLC hint.

    The substitution list catches Prosperity, Contact, and Signal IDs that
    contain none of DLC_KEYWORDS. Keywords stay so unlisted reskins still count.
    """
    if subtype in DLC_TO_BASE_PAIRS:
        return True
    lowered = subtype.lower()
    return any(keyword in lowered for keyword in DLC_KEYWORDS)


def _is_connector_subtype(subtype: str) -> bool:
    return "connector" in subtype.lower()


def compute_se2_readiness(block_counts: Dict[str, int]) -> SE2Readiness:
    """
    Score a blueprint for Space Engineers 2 transition risk.

    DLC blocks, programmable blocks, and mechanical subgrids each reduce
    the score. The floor is 20 so even dense grids remain comparable.
    Connectors are counted for the official projection note and do not
    change the score: most ships have one, and scoring them would hide
    the other risks.
    """
    dlc_count = 0
    script_count = 0
    subgrid_count = 0
    connector_count = 0
    dlc_subtypes: List[str] = []

    for subtype, qty in block_counts.items():
        try:
            amount = int(qty)
        except (TypeError, ValueError):
            continue
        if amount <= 0:
            continue
        subtype_lower = subtype.lower()
        if _is_dlc_subtype(subtype):
            dlc_count += amount
            dlc_subtypes.append(subtype)
        if "programmable" in subtype_lower:
            script_count += amount
        if any(keyword in subtype_lower for keyword in MECHANICAL_KEYWORDS):
            subgrid_count += amount
        if _is_connector_subtype(subtype):
            connector_count += amount

    score = 100
    score -= min(25, dlc_count * 5)
    score -= min(25, script_count * 10)
    score -= min(30, subgrid_count * 15)
    score = max(20, score)

    if score >= 90:
        status = "OPTIMAL"
    elif score >= 60:
        status = "STABLE"
    elif score >= 40:
        status = "COMPLEX"
    else:
        status = "FRAGILE"

    return SE2Readiness(
        dlc_count=dlc_count,
        script_count=script_count,
        subgrid_count=subgrid_count,
        score=score,
        status=status,
        dlc_subtypes=tuple(sorted(dlc_subtypes)),
        connector_count=connector_count,
    )


def _join_names(names: tuple[str, ...] | List[str], limit: int = 6) -> str:
    shown = list(names)[:limit]
    extra = len(names) - len(shown)
    text = ", ".join(shown)
    if extra > 0:
        text += f", and {extra} more"
    return text


def format_se2_readiness_lines(
    readiness: SE2Readiness,
    *,
    display_name: str = "",
    grid_size: str = "",
    block_count: int = 0,
) -> List[str]:
    """Player-facing SE2 notes. Planning language only; no invented block IDs."""
    lines: List[str] = []
    if display_name:
        lines.append(f"SE2 planning estimate — {display_name}")
    else:
        lines.append("SE2 planning estimate")
    if grid_size or block_count:
        lines.append(f"{grid_size or 'Unknown'} grid  ·  {block_count} blocks")
    lines.append(SE2_PLANNING_BLURB)
    lines.append("")

    if readiness.dlc_count > 0:
        named = _join_names(readiness.dlc_subtypes)
        lines.append(
            f"DLC: {readiness.dlc_count} block(s) match the DLC list or a DLC name hint"
            + (f" ({named})." if named else ".")
        )
        lines.append("    Replace DLC with vanilla to make a copy that does not need those packs.")
    else:
        lines.append("DLC: none of the counted blocks matched the DLC list or a DLC name hint.")

    lines.append(
        "Blocks whose subtype IDs were never published are not flagged. "
        "The public 1.210 notes name a Prototech O2/H2 Generator, Flat Collector, "
        "Structural Platform Conveyor, Short Stairs, Passage 2 Frame, and the Prosperity Pack "
        "without subtype IDs, so those blocks stay unchanged unless an ID is already in this app."
    )
    lines.append("")

    if readiness.script_count > 0:
        lines.append(
            f"Scripts: {readiness.script_count} programmable block(s). "
            "This estimate does not check whether that C# carries over."
        )
    else:
        lines.append("Scripts: none.")

    if readiness.subgrid_count > 0:
        lines.append(
            f"Mechanical subgrids: {readiness.subgrid_count} rotor, hinge, or piston block(s)."
        )
    else:
        lines.append("Mechanical subgrids: no rotors, hinges, or pistons counted.")

    if readiness.connector_count > 0:
        lines.append(f"Connectors: {readiness.connector_count}. These do not change the score.")

    if readiness.subgrid_count > 0 or readiness.connector_count > 0:
        lines.append(
            "Space Engineers 2 still projects only the main grid when a blueprint includes "
            "connectors, rotors, or pistons. Keen's Grid Exporter does not support subgrids either."
        )
    lines.append("")

    if readiness.score >= 90:
        lines.append("Few of the tracked risks showed up. This is still only a planning estimate.")
    elif readiness.score >= 60:
        lines.append("Replace paid DLC blocks if you want a copy that does not need those packs.")
    else:
        lines.append("Scripts, DLC blocks, or mechanical subgrids need a closer look before you carry this ship over.")

    lines.append(
        "To bring a grid into Space Engineers 2, use Keen's Grid Exporter in Space Engineers 1 "
        "(chat command /export) and copy that file into the SE2 folder SE1GridsToImport. "
        "The JSON from this app is a planning file. Its names are not Keen block IDs."
    )
    return lines

