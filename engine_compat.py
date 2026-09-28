"""
Engine Compatibility and Future-Proofing Framework (SE1 VRAGE2 & SE2 VRAGE3).
Provides multi-game architecture, blueprint format detection, and cross-engine migration bridges.
"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import safe_xml
from version import __version__


class GameEngine(str, Enum):
    """Supported Space Engineers game engine generations."""
    SPACE_ENGINEERS_1 = "SE1_VRAGE2"
    SPACE_ENGINEERS_2 = "SE2_VRAGE3"


class BlueprintFormat(str, Enum):
    """Blueprint serialization formats across engine generations."""
    SE1_SBC_XML = "se1_sbc_xml"
    SE1_SBCB5_BIN = "se1_sbcb5_binary"
    SE2_JSON = "se2_json"
    SE2_VRAGE3_PKG = "se2_vrage3_package"
    UNKNOWN = "unknown"


@dataclass
class EngineCompatibilityReport:
    """Detailed engine compatibility and format report for a blueprint."""
    source_path: Path
    detected_engine: GameEngine
    detected_format: BlueprintFormat
    is_se1_compatible: bool
    is_se2_compatible: bool
    se2_migratable: bool
    unsupported_blocks: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)


# SE1 to SE2 (VRAGE3) Standard Block Translation Dictionary
SE1_TO_SE2_TRANSLATION_TABLE: Dict[str, str] = {
    # Armor Blocks (SE1 SubtypeName -> SE2 VRAGE3 SubtypeName)
    "LargeBlockArmorBlock": "VR3_Large_Armor_Cube",
    "LargeBlockArmorSlope": "VR3_Large_Armor_Slope",
    "LargeBlockArmorCorner": "VR3_Large_Armor_Corner",
    "LargeBlockArmorCornerInv": "VR3_Large_Armor_Corner_Inv",
    "LargeHeavyBlockArmorBlock": "VR3_Large_Heavy_Armor_Cube",
    "LargeHeavyBlockArmorSlope": "VR3_Large_Heavy_Armor_Slope",
    "LargeHeavyBlockArmorCorner": "VR3_Large_Heavy_Armor_Corner",
    "LargeHeavyBlockArmorCornerInv": "VR3_Large_Heavy_Armor_Corner_Inv",
    "SmallBlockArmorBlock": "VR3_Small_Armor_Cube",
    "SmallBlockArmorSlope": "VR3_Small_Armor_Slope",
    "SmallBlockArmorCorner": "VR3_Small_Armor_Corner",
    "SmallHeavyBlockArmorBlock": "VR3_Small_Heavy_Armor_Cube",

    # Power & Propulsion
    "LargeBlockBatteryBlock": "VR3_Large_Battery_Standard",
    "SmallBlockBatteryBlock": "VR3_Small_Battery_Standard",
    "LargeBlockSmallGenerator": "VR3_Large_Reactor_Small",
    "LargeBlockLargeGenerator": "VR3_Large_Reactor_Large",
    "LargeBlockLargeThrust": "VR3_Large_IonThrust_Large",
    "LargeBlockSmallThrust": "VR3_Large_IonThrust_Small",
    "LargeBlockLargeHydrogenThrust": "VR3_Large_HydroThrust_Large",
    "LargeBlockSmallHydrogenThrust": "VR3_Large_HydroThrust_Small",

    # Command & Control
    "LargeBlockCockpit": "VR3_Large_Cockpit_Enclosed",
    "Cockpit": "VR3_Small_Cockpit_Standard",
    "LargeBlockRadioAntenna": "VR3_Large_Antenna_Comm",
    "LargeBlockBeacon": "VR3_Large_Beacon_Telemetry",
    "SmallProgrammableBlock": "VR3_Small_Compute_Node",
    "LargeProgrammableBlock": "VR3_Large_Compute_Node",
}

SE2_TO_SE1_TRANSLATION_TABLE: Dict[str, str] = {v: k for k, v in SE1_TO_SE2_TRANSLATION_TABLE.items()}

_XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"
_XSI_TYPE = f"{{{_XSI_NS}}}type"

# Used only when JSON has no stored original_se1_builder_type.
_BUILDER_HINTS: Tuple[Tuple[str, str], ...] = (
    ("hydrogenengine", "MyObjectBuilder_HydrogenEngine"),
    ("radioantenna", "MyObjectBuilder_RadioAntenna"),
    ("programmable", "MyObjectBuilder_ProgrammableBlock"),
    ("thrust", "MyObjectBuilder_Thrust"),
    ("cockpit", "MyObjectBuilder_Cockpit"),
    ("controlseat", "MyObjectBuilder_Cockpit"),
    ("battery", "MyObjectBuilder_BatteryBlock"),
    ("reactor", "MyObjectBuilder_Reactor"),
    ("generator", "MyObjectBuilder_Reactor"),
    ("gyro", "MyObjectBuilder_Gyro"),
    ("antenna", "MyObjectBuilder_RadioAntenna"),
    ("beacon", "MyObjectBuilder_Beacon"),
    ("cargo", "MyObjectBuilder_CargoContainer"),
    ("drill", "MyObjectBuilder_ShipDrill"),
    ("welder", "MyObjectBuilder_ShipWelder"),
    ("grinder", "MyObjectBuilder_ShipGrinder"),
)


def _local_name(value: str) -> str:
    if "}" in value:
        return value.split("}", 1)[1]
    if ":" in value:
        return value.split(":", 1)[1]
    return value


def _builder_type_from_element(block_elem: ET.Element) -> str:
    for key, value in block_elem.attrib.items():
        if key == _XSI_TYPE or key == "xsi:type":
            return _local_name(value)
    tag = _local_name(block_elem.tag)
    return tag or "MyObjectBuilder_CubeBlock"


def infer_builder_type(subtype: str) -> str:
    """Map an SE1 subtype to a builder when the original xsi:type was not stored."""
    lowered = subtype.lower()
    for needle, builder in _BUILDER_HINTS:
        if needle in lowered:
            return builder
    return "MyObjectBuilder_CubeBlock"


def _orientation_from_element(block_elem: ET.Element) -> Optional[Dict[str, str]]:
    orient = block_elem.find("BlockOrientation")
    if orient is None:
        return None
    forward = orient.attrib.get("Forward")
    up = orient.attrib.get("Up")
    if not forward and not up:
        return None
    return {"forward": forward or "Forward", "up": up or "Up"}


def _entity_id_from_element(block_elem: ET.Element) -> Optional[str]:
    entity = block_elem.find("EntityId")
    if entity is None or not entity.text or not entity.text.strip():
        return None
    return entity.text.strip()


def _axis_int(elem: Optional[ET.Element], axis: str) -> int:
    if elem is None:
        return 0
    raw = elem.attrib.get(axis, "0")
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 0


def _iter_migration_grids(root: ET.Element) -> List[ET.Element]:
    grids = root.findall(".//CubeGrids/CubeGrid")
    if grids:
        return grids
    return [grid for grid in root.findall(".//CubeGrid") if grid.find("CubeBlocks") is not None]


def _subtype_text(block_elem: ET.Element) -> str:
    sub_name = block_elem.find("SubtypeName")
    sub_id = block_elem.find("SubtypeId")
    st_elem = sub_name if sub_name is not None else sub_id
    if st_elem is not None and st_elem.text and st_elem.text.strip():
        return st_elem.text.strip()
    return "UnknownBlock"


def _se1_subtype_from_json(block: Dict[str, Any]) -> Tuple[str, bool]:
    """Return the SE1 subtype and whether it was a real SE2 translation.

    Unmapped blocks stay on their original subtype. VR3_Legacy_* is only
    recovered for older payloads and is not treated as a real VRAGE3 block.
    Unknown ids are not replaced with armor.
    """
    original = block.get("original_se1_subtype")
    se2_st = str(block.get("subtype") or "")
    if isinstance(original, str) and original.strip():
        translated = bool(block.get("se2_mapped")) or se2_st in SE2_TO_SE1_TRANSLATION_TABLE
        return original.strip(), translated
    if se2_st in SE2_TO_SE1_TRANSLATION_TABLE:
        return SE2_TO_SE1_TRANSLATION_TABLE[se2_st], True
    if se2_st.startswith("VR3_Legacy_"):
        recovered = se2_st[len("VR3_Legacy_"):]
        return recovered or se2_st, False
    return se2_st or "UnknownBlock", False


def _resolve_builder_type(block: Dict[str, Any], se1_subtype: str) -> str:
    stored = block.get("original_se1_builder_type")
    if isinstance(stored, str) and stored.strip():
        return stored.strip()
    return infer_builder_type(se1_subtype)


def _orientation_from_json(block: Dict[str, Any]) -> Optional[Tuple[str, str]]:
    orientation = block.get("orientation")
    if not isinstance(orientation, dict):
        return None
    forward = orientation.get("forward") or orientation.get("Forward")
    up = orientation.get("up") or orientation.get("Up")
    if not forward and not up:
        return None
    return (str(forward or "Forward"), str(up or "Up"))


def _entity_id_from_json(block: Dict[str, Any]) -> Optional[str]:
    for key in ("original_se1_entity_id", "entity_id"):
        value = block.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


class EngineVersionDetector:
    """Detects Space Engineers version and blueprint serialization format."""

    @classmethod
    def detect_file_format(cls, path: Path) -> BlueprintFormat:
        path = Path(path)
        if not path.exists():
            return BlueprintFormat.UNKNOWN

        if path.is_dir():
            sbc2_file = path / "bp.sbc2"
            json_file = path / "blueprint.json"
            sbc_file = path / "bp.sbc"
            if sbc2_file.exists():
                return BlueprintFormat.SE2_VRAGE3_PKG
            if json_file.exists():
                return BlueprintFormat.SE2_JSON
            if sbc_file.exists():
                return BlueprintFormat.SE1_SBC_XML
            return BlueprintFormat.UNKNOWN

        suffix = path.suffix.lower()
        if suffix == ".json":
            return BlueprintFormat.SE2_JSON
        if suffix == ".sbc2":
            return BlueprintFormat.SE2_VRAGE3_PKG
        if suffix == ".sbc":
            return BlueprintFormat.SE1_SBC_XML
        if suffix == ".sbcb5":
            return BlueprintFormat.SE1_SBCB5_BIN

        # Content sniffing
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                header = f.read(512).strip()
            if header.startswith("{") or '"CubeGrids"' in header:
                return BlueprintFormat.SE2_JSON
            if "<Definitions" in header or "<ShipBlueprint" in header:
                return BlueprintFormat.SE1_SBC_XML
        except Exception:
            pass  # unreadable file; fall through to UNKNOWN

        return BlueprintFormat.UNKNOWN

    @classmethod
    def detect_engine(cls, path: Path) -> GameEngine:
        fmt = cls.detect_file_format(path)
        if fmt in (BlueprintFormat.SE2_JSON, BlueprintFormat.SE2_VRAGE3_PKG):
            return GameEngine.SPACE_ENGINEERS_2
        return GameEngine.SPACE_ENGINEERS_1

    @classmethod
    def inspect_compatibility(cls, blueprint_path: Path) -> EngineCompatibilityReport:
        blueprint_path = Path(blueprint_path)
        fmt = cls.detect_file_format(blueprint_path)
        engine = cls.detect_engine(blueprint_path)

        unsupported: List[str] = []
        notes: List[str] = []

        if engine == GameEngine.SPACE_ENGINEERS_1:
            notes.append("Space Engineers 1 (VRAGE2) native blueprint.")
            file_to_scan = blueprint_path / "bp.sbc" if blueprint_path.is_dir() else blueprint_path
            if file_to_scan.exists() and file_to_scan.is_file():
                try:
                    tree = safe_xml.parse(file_to_scan)
                    for block in tree.getroot().findall(".//CubeGrid/CubeBlocks/*"):
                        sub_name = block.find("SubtypeName")
                        sub_id = block.find("SubtypeId")
                        st_elem = sub_name if sub_name is not None else sub_id
                        st = st_elem.text.strip() if (st_elem is not None and st_elem.text) else None
                        if st and st not in SE1_TO_SE2_TRANSLATION_TABLE:
                            if st not in unsupported:
                                unsupported.append(st)
                except Exception as exc:
                    notes.append(f"Warning during SBC inspection: {exc}")

            return EngineCompatibilityReport(
                source_path=blueprint_path,
                detected_engine=GameEngine.SPACE_ENGINEERS_1,
                detected_format=fmt,
                is_se1_compatible=True,
                is_se2_compatible=False,
                se2_migratable=True,
                unsupported_blocks=unsupported,
                notes=notes,
            )
        else:
            notes.append("Space Engineers 2 (VRAGE3) native blueprint.")
            return EngineCompatibilityReport(
                source_path=blueprint_path,
                detected_engine=GameEngine.SPACE_ENGINEERS_2,
                detected_format=fmt,
                is_se1_compatible=False,
                is_se2_compatible=True,
                se2_migratable=False,
                unsupported_blocks=[],
                notes=notes,
            )


class SE2MigrationBridge:
    """Translates blueprints between Space Engineers 1 and Space Engineers 2 formats."""

    @classmethod
    def migrate_se1_to_se2(cls, se1_bp_path: Path, output_dir: Optional[Path] = None) -> Tuple[Path, int, int]:
        """
        Converts a Space Engineers 1 SBC XML blueprint into a Space Engineers 2 (VRAGE3 JSON) structure.
        """
        se1_bp_path = Path(se1_bp_path)
        if se1_bp_path.is_file() and se1_bp_path.name == "bp.sbc":
            bp_folder = se1_bp_path.parent
            sbc_file = se1_bp_path
        else:
            bp_folder = se1_bp_path
            sbc_file = se1_bp_path / "bp.sbc"

        if not sbc_file.exists():
            raise FileNotFoundError(f"Missing SE1 blueprint file: {sbc_file}")

        target_dir = output_dir if output_dir else bp_folder.parent / f"SE2_{bp_folder.name}"
        target_dir.mkdir(parents=True, exist_ok=True)

        tree = safe_xml.parse(sbc_file)
        root = tree.getroot()

        scanned = 0
        converted = 0

        grids_data: List[Dict[str, Any]] = []
        for grid_elem in _iter_migration_grids(root):
            custom_name_elem = grid_elem.find("CustomName")
            custom_name = custom_name_elem.text.strip() if custom_name_elem is not None and custom_name_elem.text else "Grid"
            grid_size_elem = grid_elem.find("GridSizeEnum")
            grid_size = grid_size_elem.text.strip() if grid_size_elem is not None and grid_size_elem.text else "Large"

            blocks_list: List[Dict[str, Any]] = []
            for block_elem in grid_elem.findall(".//CubeBlocks/*"):
                scanned += 1
                st = _subtype_text(block_elem)
                mapped = st in SE1_TO_SE2_TRANSLATION_TABLE
                if mapped:
                    se2_subtype = SE1_TO_SE2_TRANSLATION_TABLE[st]
                    converted += 1
                else:
                    # Pass the original SE1 subtype through. Do not mint a
                    # VR3_* id the game could treat as real content.
                    se2_subtype = st

                min_elem = block_elem.find("Min")
                block_payload: Dict[str, Any] = {
                    "subtype": se2_subtype,
                    "se2_mapped": mapped,
                    "passthrough": not mapped,
                    "original_se1_subtype": st,
                    "original_se1_builder_type": _builder_type_from_element(block_elem),
                    "position": {
                        "x": _axis_int(min_elem, "x"),
                        "y": _axis_int(min_elem, "y"),
                        "z": _axis_int(min_elem, "z"),
                    },
                }
                entity_id = _entity_id_from_element(block_elem)
                if entity_id is not None:
                    block_payload["original_se1_entity_id"] = entity_id
                orientation = _orientation_from_element(block_elem)
                if orientation is not None:
                    block_payload["orientation"] = orientation
                blocks_list.append(block_payload)

            grids_data.append({
                "name": custom_name,
                "grid_size": grid_size,
                "blocks": blocks_list,
            })

        se2_payload = {
            "engine_target": GameEngine.SPACE_ENGINEERS_2.value,
            "format_version": "3.0.0",
            "blueprint_name": bp_folder.name,
            "grids": grids_data,
            "generator": f"MBX-{__version__}",
        }

        output_json = target_dir / "blueprint.json"
        with open(output_json, "w", encoding="utf-8") as f:
            json.dump(se2_payload, f, indent=2)

        return target_dir, scanned, converted

    @classmethod
    def migrate_se2_to_se1(cls, se2_json_path: Path, output_dir: Optional[Path] = None) -> Tuple[Path, int, int]:
        """
        Translates a Space Engineers 2 JSON blueprint back into a Space Engineers 1 SBC XML file.
        """
        se2_json_path = Path(se2_json_path)
        if se2_json_path.is_dir():
            json_file = se2_json_path / "blueprint.json"
        else:
            json_file = se2_json_path

        if not json_file.exists():
            raise FileNotFoundError(f"Missing SE2 JSON file: {json_file}")

        with open(json_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        target_dir = output_dir if output_dir else json_file.parent.parent / f"SE1_{data.get('blueprint_name', 'Converted')}"
        target_dir.mkdir(parents=True, exist_ok=True)

        scanned = 0
        converted = 0

        ET.register_namespace("xsi", _XSI_NS)
        ET.register_namespace("xsd", "http://www.w3.org/2001/XMLSchema")
        root = ET.Element("Definitions")
        ship_bps = ET.SubElement(root, "ShipBlueprints")
        ship_bp = ET.SubElement(ship_bps, "ShipBlueprint")
        ship_bp.set(_XSI_TYPE, "MyObjectBuilder_ShipBlueprintDefinition")

        cube_grids = ET.SubElement(ship_bp, "CubeGrids")
        for grid_data in data.get("grids", []):
            if not isinstance(grid_data, dict):
                continue
            cg = ET.SubElement(cube_grids, "CubeGrid")
            ET.SubElement(cg, "CustomName").text = str(grid_data.get("name") or "Grid")
            ET.SubElement(cg, "GridSizeEnum").text = str(grid_data.get("grid_size") or "Large")
            cb = ET.SubElement(cg, "CubeBlocks")

            for block in grid_data.get("blocks", []):
                if not isinstance(block, dict):
                    continue
                scanned += 1
                se1_st, translated = _se1_subtype_from_json(block)
                if translated:
                    converted += 1

                b_elem = ET.SubElement(cb, "MyObjectBuilder_CubeBlock")
                b_elem.set(_XSI_TYPE, _resolve_builder_type(block, se1_st))
                ET.SubElement(b_elem, "SubtypeName").text = se1_st
                entity_id = _entity_id_from_json(block)
                if entity_id is not None:
                    ET.SubElement(b_elem, "EntityId").text = entity_id
                orientation = _orientation_from_json(block)
                if orientation is not None:
                    ET.SubElement(b_elem, "BlockOrientation").attrib.update(
                        {"Forward": orientation[0], "Up": orientation[1]}
                    )
                pos = block.get("position")
                if not isinstance(pos, dict):
                    pos = {}
                ET.SubElement(b_elem, "Min").attrib.update({
                    "x": str(pos.get("x", 0)),
                    "y": str(pos.get("y", 0)),
                    "z": str(pos.get("z", 0)),
                })

        tree: ET.ElementTree[ET.Element] = ET.ElementTree(root)
        out_sbc = target_dir / "bp.sbc"
        safe_xml.safe_write(tree, out_sbc)

        return target_dir, scanned, converted
