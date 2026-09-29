"""Locks the v3.2.1 catalog and the internal fixes from the 2026-09-28 gap pass.

These tests do not claim the pairs match a Space Engineers install.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from blueprint_scanner import BlueprintScanner
from engine_compat import SE2MigrationBridge
from mappings.armor import ARMOR_PAIRS
from mappings.dlc_substitution import DLC_TO_BASE_PAIRS
from mappings.functional import FUNCTIONAL_PAIRS
from mappings.prototech import PROTOTECH_TO_VANILLA_PAIRS, VANILLA_TO_PROTOTECH_PAIRS
from mappings.registry import (
    MappingValidationError,
    authored_exchange_targets,
    build_registry,
    coerce_mergeable_categories,
)
from mappings.thrusters import THRUSTER_PAIRS
from mappings.weapons import WEAPON_PAIRS
from pb_doctor.script_fixer import ScriptFixer
from pb_doctor.script_validator import PBScriptValidator
from se_armor_replacer import ArmorBlockReplacer

ROOT = Path(__file__).resolve().parents[1]

SBC = """<?xml version="1.0" encoding="utf-8"?>
<Definitions xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <ShipBlueprints>
    <ShipBlueprint>
      <CubeGrids>
        <CubeGrid>
          <GridSizeEnum>Large</GridSizeEnum>
          <CubeBlocks>
            <MyObjectBuilder_CubeBlock xsi:type="MyObjectBuilder_CubeBlock">
              <SubtypeName>LargeAssembler</SubtypeName>
              <Min x="0" y="0" z="0" />
            </MyObjectBuilder_CubeBlock>
            <MyObjectBuilder_CubeBlock xsi:type="MyObjectBuilder_CubeBlock">
              <SubtypeName>LargeIndustrialAssembler</SubtypeName>
              <Min x="1" y="0" z="0" />
            </MyObjectBuilder_CubeBlock>
            <MyObjectBuilder_CubeBlock xsi:type="MyObjectBuilder_CubeBlock">
              <SubtypeName>LargeHeavyBlockArmorBlock</SubtypeName>
              <Min x="2" y="0" z="0" />
            </MyObjectBuilder_CubeBlock>
          </CubeBlocks>
        </CubeGrid>
      </CubeGrids>
    </ShipBlueprint>
  </ShipBlueprints>
</Definitions>
"""


def test_catalog_counts_match_v321_notes():
    assert len(ARMOR_PAIRS) == 70
    assert len(THRUSTER_PAIRS) == 6
    assert len(WEAPON_PAIRS) == 5
    assert len(FUNCTIONAL_PAIRS) == 6
    assert len(DLC_TO_BASE_PAIRS) == 96
    assert len(set(DLC_TO_BASE_PAIRS.values())) == 45
    assert len(VANILLA_TO_PROTOTECH_PAIRS) == 23
    assert len(PROTOTECH_TO_VANILLA_PAIRS) == 36
    costs = json.loads((ROOT / "data" / "block_costs.json").read_text(encoding="utf-8"))
    assert costs["metadata"]["version"] == "1.0"
    assert len(costs["blocks"]) == 48


def test_reverse_all_builtin_skips_one_way_dlc(tmp_path: Path):
    replacer = ArmorBlockReplacer(
        include_profiles=False,
        enabled_categories=["all"],
        reverse=True,
    )
    assert "dlc_substitution" in replacer.enabled_categories
    assert replacer.mapping["LargeAssembler"] == "BasicAssembler"
    assert "LargeIndustrialAssembler" not in replacer.mapping
    assert replacer.mapping["LargeHeavyBlockArmorBlock"] == "LargeBlockArmorBlock"

    blueprint = tmp_path / "ship"
    blueprint.mkdir()
    (blueprint / "bp.sbc").write_text(SBC, encoding="utf-8")
    replacer.process_blueprint(str(blueprint), dry_run=True)
    changes = dict(replacer.change_log)
    assert changes["LargeAssembler"] == "BasicAssembler"
    assert changes["LargeHeavyBlockArmorBlock"] == "LargeBlockArmorBlock"
    assert "LargeIndustrialAssembler" not in changes


def test_reverse_dlc_alone_is_rejected():
    with pytest.raises(MappingValidationError, match="one-way"):
        ArmorBlockReplacer(
            include_profiles=False,
            enabled_categories=["dlc_substitution"],
            reverse=True,
        )


def test_scanner_default_reverse_does_not_crash():
    scanner = BlueprintScanner()
    scanner.set_reverse(True)
    assert scanner._mapping["LargeAssembler"] == "BasicAssembler"


def test_colliding_saved_categories_fall_back_to_armor():
    registry = build_registry()
    names, repaired = coerce_mergeable_categories(registry, ["prototech", "weapons"])
    assert repaired is True
    assert names == ["armor"]
    ok, repaired_ok = coerce_mergeable_categories(registry, ["armor", "thrusters"])
    assert repaired_ok is False
    assert ok == ["armor", "thrusters"]


def test_pb_entry_points_ignore_comments_and_strings():
    commented = '// void Main(string argument)\npublic void Update() {\n    Echo("idle");\n}\n'
    report = PBScriptValidator.validate_script(commented)
    assert report.has_main_method is False
    assert any(item.rule_id == "MISSING_MAIN" for item in report.diagnostics)

    quoted = 'public void Update() {\n    Echo("void Main(string argument)");\n}\n'
    quoted_report = PBScriptValidator.validate_script(quoted)
    assert quoted_report.has_main_method is False

    real = "public void Main(string argument, UpdateType updateSource) {\n    Echo(\"ok\");\n}\n"
    real_report = PBScriptValidator.validate_script(real)
    assert real_report.has_main_method is True
    assert not any(item.rule_id == "MISSING_MAIN" for item in real_report.diagnostics)

    fixed, fixes = ScriptFixer.fix_script(commented)
    assert any("Main" in note for note in fixes)
    assert "void Main" in fixed


def test_exchange_suggestions_stay_inside_authored_tables():
    registry = build_registry()
    targets = authored_exchange_targets(
        registry,
        extra_one_way=PROTOTECH_TO_VANILLA_PAIRS,
    )
    assert targets["IndustrialCockpit"] == ["LargeBlockCockpit"]
    assert "Cockpit" not in targets["IndustrialCockpit"]
    assert "LargePrototechGyro" not in targets.get("LargeGyro", [])
    assert "SmallPrototechReactor" not in {
        item for values in targets.values() for item in values
    }
    generator_targets = set(targets["LargeBlockSmallGenerator"])
    assert "LargeBlockLargeGenerator" in generator_targets
    assert "LargePrototechGeneratorSmall" in generator_targets
    assert "LargePrototechReactor" not in generator_targets

    panel_source = (ROOT / "ui" / "selective_exchange_panel.py").read_text(encoding="utf-8")
    assert "PrototechGyro" not in panel_source
    assert 'replace("Industrial"' not in panel_source


def test_se2_export_labels_placeholders(tmp_path: Path):
    blueprint = tmp_path / "ship"
    blueprint.mkdir()
    (blueprint / "bp.sbc").write_text(SBC, encoding="utf-8")
    out_dir, _scanned, _converted = SE2MigrationBridge.migrate_se1_to_se2(blueprint)
    payload = json.loads((out_dir / "blueprint.json").read_text(encoding="utf-8"))
    assert payload["translation_status"] == "unverified_internal_placeholders"
    assert "not Keen" in payload["note"]
    subtypes = {block["subtype"] for grid in payload["grids"] for block in grid["blocks"]}
    assert subtypes
    assert all(name.startswith("VR3_") for name in subtypes)
