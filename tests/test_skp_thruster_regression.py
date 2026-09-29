"""Regression on Avery's SKP burn-and-turn blueprint.

Armor light→heavy must keep every thruster CubeBlock (subtype, xsi:type, and
EntityId). This fails if a convert path remaps or drops those blocks.
"""

from __future__ import annotations

import shutil
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

from blueprint_converter import BlueprintConverter
from se_armor_replacer import ArmorBlockReplacer

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "skp_burn_and_turn_original.sbc"
XSI_TYPE = "{http://www.w3.org/2001/XMLSchema-instance}type"

THRUST_COUNTS = {
    "STR350_Flat": 16,
    "STR350_Slope30_3": 16,
    "STR350_Slope30_2": 4,
    "ARYLNX_SCIRCOCCO_Epstein_Drive": 1,
}

ARMOR_DELTAS = {
    "LargeBlockArmorBlock": (26, 0),
    "LargeHeavyBlockArmorBlock": (223, 249),
    "LargeBlockArmorSlope2Base": (2, 0),
    "LargeBlockArmorSlope2Tip": (4, 0),
    "LargeHalfSlopeArmorBlock": (6, 0),
    "LargeHeavyBlockArmorSlope2Base": (58, 60),
    "LargeHeavyBlockArmorSlope2Tip": (58, 62),
    "LargeHeavyHalfSlopeArmorBlock": (49, 55),
    "LargeArmorPanelLight": (2, 0),
    "LargeArmorPanelHeavy": (1, 3),
}


def _blocks(path: Path):
    root = ET.parse(path).getroot()
    blocks = []
    for parent in root.findall(".//CubeBlocks"):
        blocks.extend(list(parent))
    return blocks


def _subtype(block) -> str:
    node = block.find("SubtypeName")
    if node is not None and node.text:
        return node.text.strip()
    return ""


def _entity_id(block) -> str:
    node = block.find("EntityId")
    if node is not None and node.text:
        return node.text.strip()
    return ""


def _is_thrust(block) -> bool:
    return block.attrib.get(XSI_TYPE) == "MyObjectBuilder_Thrust"


def _thrust_rows(blocks):
    rows = []
    for block in blocks:
        if _is_thrust(block) or _subtype(block) in THRUST_COUNTS:
            rows.append((_entity_id(block), block.attrib.get(XSI_TYPE, ""), _subtype(block)))
    return rows


def _subtype_counts(blocks) -> Counter:
    return Counter(_subtype(block) for block in blocks)


def _prepare(tmp_path: Path) -> Path:
    folder = tmp_path / "SKP burn and turn"
    folder.mkdir()
    shutil.copy(FIXTURE, folder / "bp.sbc")
    (folder / "bp.sbcB5").write_bytes(b"stale-binary-cache")
    return folder


def _assert_thrusters_and_armor(source_blocks, converted_blocks, converted_text: str):
    assert len(source_blocks) == 966
    assert len(converted_blocks) == 966

    before = _thrust_rows(source_blocks)
    after = _thrust_rows(converted_blocks)
    assert len(before) == 37
    assert sorted(after) == sorted(before)
    assert Counter(row[2] for row in after) == THRUST_COUNTS
    assert all(row[1] == "MyObjectBuilder_Thrust" for row in after)
    assert len({row[0] for row in after}) == 37
    assert converted_text.count('xsi:type="MyObjectBuilder_Thrust"') == 37

    source_counts = _subtype_counts(source_blocks)
    converted_counts = _subtype_counts(converted_blocks)
    for subtype, (old, new) in ARMOR_DELTAS.items():
        assert source_counts[subtype] == old
        assert converted_counts[subtype] == new

    changed = {
        subtype
        for subtype in set(source_counts) | set(converted_counts)
        if source_counts[subtype] != converted_counts[subtype]
    }
    assert changed == set(ARMOR_DELTAS)

    def reactors(blocks):
        return Counter(
            (_entity_id(block), _subtype(block))
            for block in blocks
            if block.attrib.get(XSI_TYPE) == "MyObjectBuilder_Reactor"
        )

    assert reactors(source_blocks) == reactors(converted_blocks)
    assert sum(reactors(converted_blocks).values()) == 15


def test_gui_armor_light_to_heavy_preserves_skp_thrusters(tmp_path: Path):
    source = _prepare(tmp_path)
    source_blocks = _blocks(source / "bp.sbc")
    converter = BlueprintConverter(include_profiles=False)
    dest, scanned, converted = converter.create_heavy_armor_blueprint(source)

    assert scanned == 966
    assert converted == 40
    assert not (dest / "bp.sbcB5").exists()
    assert (source / "bp.sbcB5").exists()
    text = (dest / "bp.sbc").read_text(encoding="utf-8")
    _assert_thrusters_and_armor(source_blocks, _blocks(dest / "bp.sbc"), text)
    warning = converter.last_mod_block_warning
    assert "STR350_Flat  x16" in warning
    assert "STR350_Slope30_3  x16" in warning
    assert "STR350_Slope30_2  x4" in warning
    assert "ARYLNX_SCIRCOCCO_Epstein_Drive  x1" in warning
    assert "does not remove or remap" in warning


def test_cli_armor_light_to_heavy_preserves_skp_thrusters(tmp_path: Path):
    source = _prepare(tmp_path)
    source_blocks = _blocks(source / "bp.sbc")
    replacer = ArmorBlockReplacer(include_profiles=False)
    scanned, converted = replacer.process_blueprint(str(source), create_backup=False)

    assert scanned == 966
    assert converted == 40
    assert replacer.binary_cache_removed is True
    assert not (source / "bp.sbcB5").exists()
    text = (source / "bp.sbc").read_text(encoding="utf-8")
    _assert_thrusters_and_armor(source_blocks, _blocks(source / "bp.sbc"), text)
    assert "STR350_Flat  x16" in replacer.mod_block_warning
    assert "ARYLNX_SCIRCOCCO_Epstein_Drive  x1" in replacer.mod_block_warning
