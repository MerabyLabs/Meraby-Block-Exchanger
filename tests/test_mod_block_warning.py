"""Armor conversion must warn on mod subtypes and leave thrusters untouched."""

from __future__ import annotations

import io
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

import pytest

from blueprint_converter import BlueprintConverter, stage_blueprint_for_spawn
from blueprint_fixtures import write_blueprint_dir
from blueprint_mod_warning import (
    MOD_BLOCK_WARNING_DETAIL,
    MOD_BLOCK_WARNING_HEADLINE,
    QA_GATE_EXIT_CODE,
    QA_GATE_LINE,
    is_unresolved_mod_subtype,
    known_vanilla_subtypes,
)
from mappings.armor import ARMOR_PAIRS
from mappings.thrusters import THRUSTER_PAIRS
from se_armor_replacer import BINARY_CACHE_PLAYER_NOTE, ArmorBlockReplacer, BinaryCacheError, main

MOD_THRUST = (
    {"subtype": "STR350_Flat", "tag": "MyObjectBuilder_Thrust", "xsi_type": "MyObjectBuilder_Thrust"},
    {"subtype": "STR350_Slope30_3", "tag": "MyObjectBuilder_Thrust", "xsi_type": "MyObjectBuilder_Thrust"},
    {"subtype": "STR350_Slope30_2", "tag": "MyObjectBuilder_Thrust", "xsi_type": "MyObjectBuilder_Thrust"},
    {
        "subtype": "ARYLNX_SCIRCOCCO_Epstein_Drive",
        "tag": "MyObjectBuilder_Thrust",
        "xsi_type": "MyObjectBuilder_Thrust",
    },
)

VANILLA_LARGE_THRUST = (
    "LargeBlockSmallThrust",
    "LargeBlockLargeThrust",
    "LargeBlockSmallHydrogenThrust",
    "LargeBlockLargeHydrogenThrust",
    "LargeBlockSmallAtmosphericThrust",
    "LargeBlockLargeAtmosphericThrust",
)


def _thrust(subtype: str) -> dict:
    return {
        "subtype": subtype,
        "tag": "MyObjectBuilder_Thrust",
        "xsi_type": "MyObjectBuilder_Thrust",
    }


def _counts(xml: str, subtype: str) -> int:
    return xml.count(f"<SubtypeName>{subtype}</SubtypeName>")


def test_armor_pairs_do_not_remap_thrusters():
    armor_ids = set(ARMOR_PAIRS) | set(ARMOR_PAIRS.values())
    thrust_ids = set(THRUSTER_PAIRS) | set(THRUSTER_PAIRS.values())
    assert armor_ids.isdisjoint(thrust_ids)
    for subtype in armor_ids:
        assert "Thrust" not in subtype
        assert "STR350" not in subtype
        assert "ARYLNX" not in subtype


def test_known_vanilla_includes_armor_and_large_thrusters():
    known = known_vanilla_subtypes()
    assert "LargeBlockArmorBlock" in known
    assert "LargeHeavyBlockArmorBlock" in known
    assert "SmallBlockArmorBlock" in known
    for subtype in VANILLA_LARGE_THRUST:
        assert subtype in known
        assert is_unresolved_mod_subtype(subtype, known) is False


def test_mod_thruster_ids_are_unresolved_and_gyros_are_not():
    assert is_unresolved_mod_subtype("STR350_Flat") is True
    assert is_unresolved_mod_subtype("STR350_Slope30_3") is True
    assert is_unresolved_mod_subtype("ARYLNX_SCIRCOCCO_Epstein_Drive") is True
    assert is_unresolved_mod_subtype("LargeBlockGyro") is False
    assert is_unresolved_mod_subtype("LargeBlockArmorBlock") is False
    assert is_unresolved_mod_subtype("SmallBlockSmallHydrogenThrust") is False


def test_large_grid_armor_light_to_heavy_preserves_vanilla_thrusters(tmp_path: Path):
    source = write_blueprint_dir(
        tmp_path,
        "BurnAndTurn",
        [
            "LargeBlockArmorBlock",
            "LargeBlockArmorSlope",
            "LargeBlockGyro",
            *(_thrust(name) for name in VANILLA_LARGE_THRUST),
        ],
        grid_size="Large",
        extra_files=["bp.sbcB5"],
    )
    converter = BlueprintConverter(include_profiles=False)
    dest, _scanned, converted = converter.create_heavy_armor_blueprint(source)

    assert converted == 2
    assert dest.name == "HEAVYARMOR_BurnAndTurn"
    assert not (dest / "bp.sbcB5").exists()
    assert (source / "bp.sbcB5").exists()
    assert converter.last_mod_block_warning == ""

    xml = (dest / "bp.sbc").read_text(encoding="utf-8")
    assert _counts(xml, "LargeHeavyBlockArmorBlock") == 1
    assert _counts(xml, "LargeHeavyBlockArmorSlope") == 1
    assert _counts(xml, "LargeBlockArmorBlock") == 0
    for subtype in VANILLA_LARGE_THRUST:
        assert _counts(xml, subtype) == 1
    assert _counts(xml, "LargeBlockGyro") == 1


def test_small_grid_armor_light_to_heavy_still_converts(tmp_path: Path):
    source = write_blueprint_dir(
        tmp_path,
        "Drone",
        [
            "SmallBlockArmorBlock",
            _thrust("SmallBlockSmallHydrogenThrust"),
            _thrust("SmallBlockSmallThrust"),
            _thrust("SmallBlockLargeThrust"),
        ],
        grid_size="Small",
    )
    converter = BlueprintConverter(include_profiles=False)
    dest, _scanned, converted = converter.create_heavy_armor_blueprint(source)
    xml = (dest / "bp.sbc").read_text(encoding="utf-8")
    assert converted == 1
    assert _counts(xml, "SmallHeavyBlockArmorBlock") == 1
    assert _counts(xml, "SmallBlockSmallHydrogenThrust") == 1
    assert _counts(xml, "SmallBlockSmallThrust") == 1
    assert _counts(xml, "SmallBlockLargeThrust") == 1
    assert converter.last_mod_block_warning == ""


def test_armor_convert_warns_on_mod_subtypes_without_rewriting_them(tmp_path: Path):
    source = write_blueprint_dir(
        tmp_path,
        "SKP",
        ["LargeBlockArmorBlock", *MOD_THRUST],
        grid_size="Large",
        extra_files=["bp.sbcB5"],
    )
    before = (source / "bp.sbc").read_text(encoding="utf-8")
    converter = BlueprintConverter(include_profiles=False)
    dest, _scanned, converted = converter.create_heavy_armor_blueprint(source)

    assert converted == 1
    assert not (dest / "bp.sbcB5").exists()
    xml = (dest / "bp.sbc").read_text(encoding="utf-8")
    assert _counts(xml, "LargeHeavyBlockArmorBlock") == 1
    assert _counts(xml, "STR350_Flat") == 1
    assert _counts(xml, "STR350_Slope30_3") == 1
    assert _counts(xml, "STR350_Slope30_2") == 1
    assert _counts(xml, "ARYLNX_SCIRCOCCO_Epstein_Drive") == 1
    assert "STR350_Flat" in before

    warning = converter.last_mod_block_warning
    assert warning.startswith(MOD_BLOCK_WARNING_HEADLINE)
    assert MOD_BLOCK_WARNING_DETAIL in warning
    assert "does not remove or remap" in warning
    assert "STR350_Flat  x1" in warning
    assert "STR350_Slope30_3  x1" in warning
    assert "STR350_Slope30_2  x1" in warning
    assert "ARYLNX_SCIRCOCCO_Epstein_Drive  x1" in warning
    assert "LargeBlockArmorBlock" not in warning
    assert "LargeHeavyBlockArmorBlock" not in warning


def test_cli_armor_convert_prints_mod_warning_and_keeps_blocks(tmp_path: Path):
    source = write_blueprint_dir(
        tmp_path,
        "SKP",
        ["LargeBlockArmorBlock", *MOD_THRUST],
        grid_size="Large",
    )
    stdout = io.StringIO()
    stderr = io.StringIO()
    with patch(
        "sys.argv",
        ["se_armor_replacer", str(source), "--no-backup", "--no-profiles"],
    ):
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main()

    assert code == 0
    out = stdout.getvalue()
    err = stderr.getvalue()
    assert "Success!" in out
    for stream in (out, err):
        assert MOD_BLOCK_WARNING_HEADLINE in stream
        assert MOD_BLOCK_WARNING_DETAIL in stream
        assert "STR350_Flat  x1" in stream
        assert "ARYLNX_SCIRCOCCO_Epstein_Drive  x1" in stream
        assert "when you spawn the ship" in stream
        assert BINARY_CACHE_PLAYER_NOTE in stream
    xml = (source / "bp.sbc").read_text(encoding="utf-8")
    assert "STR350_Flat" in xml
    assert "ARYLNX_SCIRCOCCO_Epstein_Drive" in xml
    assert "LargeHeavyBlockArmorBlock" in xml


def test_cli_thruster_category_does_not_emit_armor_mod_warning(tmp_path: Path):
    source = write_blueprint_dir(
        tmp_path,
        "SKP",
        ["LargeBlockArmorBlock", *MOD_THRUST],
        grid_size="Large",
    )
    stdout = io.StringIO()
    stderr = io.StringIO()
    with patch(
        "sys.argv",
        [
            "se_armor_replacer",
            str(source),
            "--no-backup",
            "--no-profiles",
            "--categories",
            "thrusters",
        ],
    ):
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main()

    assert code == 0
    combined = stdout.getvalue() + stderr.getvalue()
    assert MOD_BLOCK_WARNING_HEADLINE not in combined
    xml = (source / "bp.sbc").read_text(encoding="utf-8")
    assert "STR350_Flat" in xml
    assert "LargeBlockArmorBlock" in xml
    assert "LargeHeavyBlockArmorBlock" not in xml


def test_stage_for_spawn_deletes_b5_and_gates_mod_subtypes(tmp_path: Path):
    source = write_blueprint_dir(
        tmp_path,
        "SKP",
        ["LargeBlockArmorBlock", _thrust("LargeBlockSmallThrust"), *MOD_THRUST],
        extra_files=["bp.sbcB5", "bp_reversed.sbc"],
    )
    original = (source / "bp.sbc").read_bytes()
    dest, warning, removed = stage_blueprint_for_spawn(source, tmp_path / "MerabyQA_stage")

    assert removed is True
    assert not (dest / "bp.sbcB5").exists()
    assert (dest / "bp.sbc").read_bytes() == original
    assert (dest / "bp_reversed.sbc").exists()
    assert _counts((dest / "bp.sbc").read_text(encoding="utf-8"), "LargeBlockArmorBlock") == 1
    assert _counts((dest / "bp.sbc").read_text(encoding="utf-8"), "STR350_Flat") == 1
    assert _counts((dest / "bp.sbc").read_text(encoding="utf-8"), "LargeBlockSmallThrust") == 1
    assert "STR350_Flat  x1" in warning
    assert "ARYLNX_SCIRCOCCO_Epstein_Drive  x1" in warning

    stdout = io.StringIO()
    stderr = io.StringIO()
    with patch(
        "sys.argv",
        ["se_armor_replacer", str(source), "--stage-for-spawn", str(tmp_path / "cli-stage")],
    ):
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main()
    assert code == QA_GATE_EXIT_CODE
    combined = stdout.getvalue() + stderr.getvalue()
    assert "Deleted bp.sbcB5 before spawn." in combined
    assert QA_GATE_LINE in combined
    assert "STR350_Flat  x1" in combined
    assert not (tmp_path / "cli-stage" / "bp.sbcB5").exists()


def test_stage_for_spawn_vanilla_blueprint_exits_clear(tmp_path: Path):
    source = write_blueprint_dir(
        tmp_path,
        "Drone",
        ["SmallBlockArmorBlock", _thrust("SmallBlockSmallThrust")],
        grid_size="Small",
        extra_files=["bp.sbcB5"],
    )
    stdout = io.StringIO()
    stderr = io.StringIO()
    with patch(
        "sys.argv",
        ["se_armor_replacer", str(source), "--stage-for-spawn", str(tmp_path / "drone-stage")],
    ):
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main()
    assert code == 0
    combined = stdout.getvalue() + stderr.getvalue()
    assert QA_GATE_LINE not in combined
    assert MOD_BLOCK_WARNING_HEADLINE not in combined
    assert not (tmp_path / "drone-stage" / "bp.sbcB5").exists()


def test_converted_folder_omits_b5_and_keeps_reversed_sbc(tmp_path: Path):
    """Avery: convert output is bp.sbc plus siblings such as bp_reversed.sbc, and no bp.sbcB5.

    A bp.sbcB5 written later, when Space Engineers spawns the ship, is a game bake.
    The converter must not leave one, and must not remap mod or vanilla thrusters.
    """
    source = write_blueprint_dir(
        tmp_path,
        "SKP burn and turn",
        [
            "LargeBlockArmorBlock",
            _thrust("LargeBlockSmallThrust"),
            _thrust("LargeBlockLargeThrust"),
            *MOD_THRUST,
        ],
        grid_size="Large",
        extra_files=["bp.sbcB5", "bp_reversed.sbc"],
    )
    (source / "bp_reversed.sbc").write_text("<reversed/>", encoding="utf-8")
    converter = BlueprintConverter(include_profiles=False)
    dest, _scanned, converted = converter.create_heavy_armor_blueprint(source)

    assert converted == 1
    assert converter.removed_binary_cache is True
    names = sorted(path.name for path in dest.iterdir())
    assert "bp.sbcB5" not in names
    assert "bp.sbc" in names
    assert "bp_reversed.sbc" in names
    assert (dest / "bp_reversed.sbc").read_text(encoding="utf-8") == "<reversed/>"
    xml = (dest / "bp.sbc").read_text(encoding="utf-8")
    assert _counts(xml, "LargeHeavyBlockArmorBlock") == 1
    assert _counts(xml, "LargeBlockSmallThrust") == 1
    assert _counts(xml, "LargeBlockLargeThrust") == 1
    assert _counts(xml, "STR350_Flat") == 1
    assert _counts(xml, "ARYLNX_SCIRCOCCO_Epstein_Drive") == 1
    assert "STR350_Flat  x1" in converter.last_mod_block_warning
    assert "LargeBlockSmallThrust" not in converter.last_mod_block_warning
    assert "when you spawn the ship" in BINARY_CACHE_PLAYER_NOTE


def test_converted_copy_surfaces_binary_cache_error(tmp_path: Path):
    source = write_blueprint_dir(
        tmp_path,
        "Ship",
        ["LargeBlockArmorBlock", _thrust("LargeBlockSmallThrust")],
        extra_files=["bp.sbcB5"],
    )
    real_unlink = Path.unlink

    def locked(path: Path, missing_ok: bool = False):
        if path.name.endswith("sbcB5"):
            raise PermissionError("locked by game")
        return real_unlink(path, missing_ok=missing_ok)

    converter = BlueprintConverter(include_profiles=False)
    with patch("se_armor_replacer.time.sleep", return_value=None):
        with patch.object(Path, "unlink", locked):
            with pytest.raises(BinaryCacheError, match="stale binary"):
                converter.create_converted_blueprint(source)

    dest = tmp_path / "HEAVYARMOR_Ship"
    assert not dest.exists()
    xml = (source / "bp.sbc").read_text(encoding="utf-8")
    assert "LargeBlockArmorBlock" in xml
    assert "LargeHeavyBlockArmorBlock" not in xml
    assert "LargeBlockSmallThrust" in xml
    assert (source / "bp.sbcB5").exists()


def test_dry_run_still_warns_without_writing(tmp_path: Path):
    source = write_blueprint_dir(
        tmp_path,
        "SKP",
        ["LargeBlockArmorBlock", MOD_THRUST[0]],
    )
    replacer = ArmorBlockReplacer(include_profiles=False)
    scanned, replaced = replacer.process_blueprint(str(source), dry_run=True)
    assert scanned == 2
    assert replaced == 1
    assert "STR350_Flat  x1" in replacer.mod_block_warning
    xml = (source / "bp.sbc").read_text(encoding="utf-8")
    assert "LargeBlockArmorBlock" in xml
    assert "LargeHeavyBlockArmorBlock" not in xml
