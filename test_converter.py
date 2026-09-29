"""Tests for BlueprintConverter: copy conversion, undo, prefixes, grid rescale."""

from __future__ import annotations

import io
import tempfile
import unittest
import xml.etree.ElementTree as ET
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch

from blueprint_converter import BlueprintConverter
from blueprint_fixtures import write_blueprint, write_blueprint_dir
from se_armor_replacer import ArmorBlockReplacer, BinaryCacheError, main


def _ship(tree: ET.ElementTree) -> ET.Element:
    ship = tree.find(".//ShipBlueprint")
    assert ship is not None
    return ship


class TestBlueprintConverter(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.converter = BlueprintConverter(verbose=True, include_profiles=False)

    def tearDown(self):
        self.tmp.cleanup()

    def _assert_folder_identity(self, dest: Path) -> None:
        tree = ET.parse(dest / "bp.sbc")
        ship = _ship(tree)
        id_elem = ship.find("Id")
        self.assertIsNotNone(id_elem)
        assert id_elem is not None
        self.assertEqual(id_elem.attrib.get("Type"), "MyObjectBuilder_ShipBlueprintDefinition")
        self.assertEqual(id_elem.attrib.get("Subtype"), dest.name)
        subtype_id = id_elem.find("SubtypeId")
        self.assertIsNotNone(subtype_id)
        assert subtype_id is not None
        self.assertEqual(subtype_id.text, dest.name)
        display = ship.find("DisplayName")
        self.assertIsNotNone(display)
        assert display is not None
        self.assertEqual(display.text, dest.name)

    def test_create_heavy_armor_blueprint_and_remove_binary_cache(self):
        source = write_blueprint_dir(
            self.root,
            "MyShip",
            ["LargeBlockArmorBlock"],
            extra_files=["bp.sbcB5"],
        )
        dest, scanned, converted = self.converter.create_heavy_armor_blueprint(source)
        self.assertEqual(scanned, 1)
        self.assertEqual(converted, 1)
        self.assertEqual(dest.name, "HEAVYARMOR_MyShip")
        self.assertFalse((dest / "bp.sbcB5").exists())
        self.assertTrue((source / "bp.sbcB5").exists())
        xml = (dest / "bp.sbc").read_text(encoding="utf-8")
        self.assertIn("LargeHeavyBlockArmorBlock", xml)
        self._assert_folder_identity(dest)
        source_id = ET.parse(source / "bp.sbc").find(".//ShipBlueprint/Id")
        self.assertIsNotNone(source_id)
        assert source_id is not None
        self.assertEqual(source_id.attrib.get("Subtype"), "MyShip")

    def test_reverse_prefix(self):
        converter = BlueprintConverter(reverse=True, include_profiles=False)
        source = write_blueprint_dir(self.root, "Tank", ["LargeHeavyBlockArmorBlock"])
        dest, _, converted = converter.create_converted_blueprint(source)
        self.assertEqual(converted, 1)
        self.assertEqual(dest.name, "LIGHTARMOR_Tank")
        self._assert_folder_identity(dest)

    def test_multi_category_prefix(self):
        converter = BlueprintConverter(
            enabled_categories=["armor", "thrusters"],
            include_profiles=False,
        )
        source = write_blueprint_dir(self.root, "Fighter", ["LargeBlockArmorBlock"])
        dest, _, _ = converter.create_converted_blueprint(source)
        self.assertEqual(dest.name, "CONVERTED_Fighter")
        self._assert_folder_identity(dest)

    def test_overwrite_existing_destination(self):
        source = write_blueprint_dir(self.root, "Ship", ["LargeBlockArmorBlock"])
        first, _, _ = self.converter.create_converted_blueprint(source)
        marker = first / "marker.txt"
        marker.write_text("old", encoding="utf-8")
        second, _, converted = self.converter.create_converted_blueprint(source)
        self.assertEqual(first, second)
        self.assertEqual(converted, 1)
        self.assertFalse(marker.exists())

    def test_undo_last_conversion(self):
        source = write_blueprint_dir(self.root, "Ship", ["LargeBlockArmorBlock"])
        dest, _, _ = self.converter.create_converted_blueprint(source)
        self.assertTrue(dest.exists())
        undone = self.converter.undo_last_conversion()
        self.assertEqual(undone, dest)
        self.assertFalse(dest.exists())
        self.assertIsNone(self.converter.undo_last_conversion())

    def test_delete_converted_blueprint(self):
        source = write_blueprint_dir(self.root, "Ship", ["LargeBlockArmorBlock"])
        dest, _, _ = self.converter.create_converted_blueprint(source)
        self.assertTrue(self.converter.delete_converted_blueprint(source))
        self.assertFalse(dest.exists())
        self.assertFalse(self.converter.delete_heavy_armor_blueprint(source))

    def test_destination_exists_check(self):
        source = write_blueprint_dir(self.root, "Ship", ["LargeBlockArmorBlock"])
        self.assertFalse(self.converter.check_destination_exists(source))
        self.converter.create_converted_blueprint(source)
        self.assertTrue(self.converter.check_destination_exists(source))

    def test_missing_source_raises(self):
        with self.assertRaises(FileNotFoundError):
            self.converter.create_converted_blueprint(self.root / "missing")

    def test_file_instead_of_directory_raises(self):
        file_path = self.root / "bp.sbc"
        file_path.write_text("<xml/>", encoding="utf-8")
        with self.assertRaises(ValueError):
            self.converter.create_converted_blueprint(file_path)

    def test_directory_without_bp_raises(self):
        empty = self.root / "Empty"
        empty.mkdir()
        with self.assertRaises(ValueError):
            self.converter.create_converted_blueprint(empty)

    def test_dlc_vanillafy_conversion(self):
        converter = BlueprintConverter(
            enabled_categories=["dlc_substitution"],
            include_profiles=False,
        )
        source = write_blueprint_dir(
            self.root,
            "DLCShip",
            ["LargeBlockSmallThrustSciFi", "IndustrialCockpit"],
        )
        dest, scanned, converted = converter.create_converted_blueprint(source)
        self.assertEqual(scanned, 2)
        self.assertEqual(converted, 2)
        xml = (dest / "bp.sbc").read_text(encoding="utf-8")
        self.assertIn("LargeBlockSmallThrust", xml)
        self.assertIn("LargeBlockCockpit", xml)
        self.assertNotIn("SciFi", xml)
        self.assertNotIn("IndustrialCockpit", xml)
        self._assert_folder_identity(dest)

    def test_thruster_and_weapon_conversion(self):
        converter = BlueprintConverter(
            enabled_categories=["thrusters", "weapons"],
            include_profiles=False,
        )
        source = write_blueprint_dir(
            self.root,
            "Combat",
            ["LargeBlockSmallThrust", "LargeGatlingTurret"],
        )
        dest, _, converted = converter.create_converted_blueprint(source)
        self.assertEqual(converted, 2)
        xml = (dest / "bp.sbc").read_text(encoding="utf-8")
        self.assertIn("LargeBlockLargeThrust", xml)
        self.assertIn("LargeAutocannonTurret", xml)

    def test_functional_conversion(self):
        converter = BlueprintConverter(
            enabled_categories=["functional"],
            include_profiles=False,
        )
        source = write_blueprint_dir(self.root, "Factory", ["BasicRefinery", "BasicAssembler"])
        _, _, converted = converter.create_converted_blueprint(source)
        self.assertEqual(converted, 2)

    def test_selective_and_survival_and_prototech_sync_identity(self):
        source = write_blueprint_dir(
            self.root,
            "Yard",
            ["LargeBlockLargeThrust", "LargePrototechBattery"],
        )
        selective, _, selective_converted = self.converter.create_selective_converted_blueprint(
            source,
            {"LargeBlockLargeThrust": "LargeBlockSmallThrust"},
            selected_subtypes=["LargeBlockLargeThrust"],
        )
        self.assertEqual(selective.name, "Custom_Yard")
        self.assertEqual(selective_converted, 1)
        self._assert_folder_identity(selective)

        survival, _, survival_converted = self.converter.survival_sanity_prototech(source)
        self.assertEqual(survival.name, "SURVIVAL_READY_Yard")
        self.assertGreaterEqual(survival_converted, 1)
        self._assert_folder_identity(survival)
        survival_xml = (survival / "bp.sbc").read_text(encoding="utf-8")
        self.assertIn("LargeBlockBatteryBlock", survival_xml)
        self.assertNotIn("LargePrototechBattery", survival_xml)

        prototech, _, prototech_converted = self.converter.upgrade_to_prototech(source)
        self.assertEqual(prototech.name, "PROTOTECH_Yard")
        self.assertGreaterEqual(prototech_converted, 1)
        self._assert_folder_identity(prototech)

    def test_identity_sync_creates_missing_ship_fields(self):
        folder = self.root / "Bare"
        folder.mkdir()
        write_blueprint(folder / "bp.sbc", ["LargeBlockArmorBlock"])
        dest, _, _ = self.converter.create_converted_blueprint(folder)
        self.assertEqual(dest.name, "HEAVYARMOR_Bare")
        tree = ET.parse(dest / "bp.sbc")
        ship = _ship(tree)
        id_elem = ship.find("Id")
        self.assertIsNotNone(id_elem)
        assert id_elem is not None
        self.assertEqual(id_elem.attrib.get("Type"), "MyObjectBuilder_ShipBlueprintDefinition")
        self.assertEqual(id_elem.attrib.get("Subtype"), dest.name)
        self.assertIsNone(id_elem.find("SubtypeId"))
        self.assertEqual(ship.findtext("DisplayName"), dest.name)

    def test_scale_grid_large_to_small_scales_coords_and_keeps_inner_size(self):
        source = write_blueprint_dir(
            self.root,
            "BigGrid",
            [
                {"subtype": "LargeBlockLargeThrust", "min": (2, 0, 1)},
                {"subtype": "LargeBlockArmorBlock", "min": (0, 0, 0)},
            ],
            grid_size="Large",
        )
        dest, scanned, converted = self.converter.scale_grid_size(source, "Small")
        self.assertEqual(scanned, 2)
        self.assertEqual(converted, 2)
        self.assertTrue(dest.name.startswith("SCALED_SMALL_"))
        self._assert_folder_identity(dest)

        tree = ET.parse(dest / "bp.sbc")
        self.assertEqual(tree.find(".//CubeGrid/GridSizeEnum").text, "Small")
        subtypes = [elem.text for elem in tree.findall(".//SubtypeName")]
        self.assertIn("SmallBlockLargeThrust", subtypes)
        self.assertNotIn("SmallBlockSmallThrust", subtypes)
        self.assertIn("SmallBlockArmorBlock", subtypes)

        mins = tree.findall(".//Min")
        coords = {(m.attrib["x"], m.attrib["y"], m.attrib["z"]) for m in mins}
        self.assertIn(("10", "0", "5"), coords)
        self.assertIn(("0", "0", "0"), coords)

    def test_scale_grid_walks_typed_sibling_that_is_not_cubeblock_tag(self):
        source = write_blueprint_dir(
            self.root,
            "Typed",
            [
                {
                    "subtype": "LargeBlockLargeThrust",
                    "min": (2, 0, 0),
                    "tag": "MyObjectBuilder_Thrust",
                    "xsi_type": "MyObjectBuilder_Thrust",
                }
            ],
            grid_size="Large",
        )
        dest, scanned, converted = self.converter.scale_grid_size(source, "Small")
        self.assertEqual(scanned, 1)
        self.assertEqual(converted, 1)
        tree = ET.parse(dest / "bp.sbc")
        blocks = list(tree.find(".//CubeBlocks"))
        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0].tag, "MyObjectBuilder_Thrust")
        self.assertNotEqual(blocks[0].tag, "MyObjectBuilder_CubeBlock")
        self.assertEqual(blocks[0].findtext("SubtypeName"), "SmallBlockLargeThrust")
        self.assertNotEqual(blocks[0].findtext("SubtypeName"), "SmallBlockSmallThrust")
        min_elem = blocks[0].find("Min")
        self.assertIsNotNone(min_elem)
        assert min_elem is not None
        self.assertEqual(min_elem.attrib["x"], "10")

    def test_scale_grid_does_not_rewrite_mid_string_large_or_small(self):
        source = write_blueprint_dir(
            self.root,
            "Mid",
            [
                {"subtype": "BlockLargeWidget", "min": (1, 0, 0)},
                {"subtype": "WidgetSmBlock", "min": (0, 2, 0)},
            ],
            grid_size="Large",
        )
        dest, scanned, converted = self.converter.scale_grid_size(source, "Small")
        self.assertEqual(scanned, 2)
        self.assertEqual(converted, 0)
        subtypes = {elem.text for elem in ET.parse(dest / "bp.sbc").findall(".//SubtypeName")}
        self.assertEqual(subtypes, {"BlockLargeWidget", "WidgetSmBlock"})

    def test_scale_grid_lowercase_prefix(self):
        source = write_blueprint_dir(
            self.root,
            "Lower",
            [{"subtype": "largeBlockArmorBlock", "min": (1, 0, 0)}],
            grid_size="Large",
        )
        dest, scanned, converted = self.converter.scale_grid_size(source, "Small")
        self.assertEqual(scanned, 1)
        self.assertEqual(converted, 1)
        self.assertEqual(
            ET.parse(dest / "bp.sbc").findtext(".//SubtypeName"),
            "smallBlockArmorBlock",
        )

    def test_scale_grid_small_to_large(self):
        source = write_blueprint_dir(
            self.root,
            "SmallGrid",
            [{"subtype": "SmallBlockArmorBlock", "min": (10, 0, 5)}],
            grid_size="Small",
        )
        dest, scanned, converted = self.converter.scale_grid_size(source, "Large")
        self.assertEqual(scanned, 1)
        self.assertEqual(converted, 1)
        tree = ET.parse(dest / "bp.sbc")
        self.assertEqual(tree.find(".//CubeGrid/GridSizeEnum").text, "Large")
        self.assertEqual(tree.find(".//SubtypeName").text, "LargeBlockArmorBlock")
        min_elem = tree.find(".//Min")
        self.assertIsNotNone(min_elem)
        assert min_elem is not None
        self.assertEqual(min_elem.attrib["x"], "2")
        self.assertEqual(min_elem.attrib["z"], "1")
        self._assert_folder_identity(dest)

    def test_scale_grid_small_to_large_truncates_negative_mins_toward_zero(self):
        source = write_blueprint_dir(
            self.root,
            "NegGrid",
            [
                {"subtype": "SmallBlockArmorBlock", "min": (-1, -5, -6)},
                {"subtype": "SmallBlockArmorBlock", "min": (4, 0, -10)},
            ],
            grid_size="Small",
        )
        dest, scanned, converted = self.converter.scale_grid_size(source, "Large")
        self.assertEqual(scanned, 2)
        self.assertEqual(converted, 2)
        tree = ET.parse(dest / "bp.sbc")
        mins = {(m.attrib["x"], m.attrib["y"], m.attrib["z"]) for m in tree.findall(".//Min")}
        # -1/5 → 0, -5/5 → -1, -6/5 → -1; 4/5 → 0, -10/5 → -2
        self.assertIn(("0", "-1", "-1"), mins)
        self.assertIn(("0", "0", "-2"), mins)
        self.assertNotIn(("-1", "-1", "-2"), mins)

    def test_scale_invalid_size(self):
        source = write_blueprint_dir(self.root, "Ship", ["LargeBlockArmorBlock"])
        with self.assertRaises(ValueError):
            self.converter.scale_grid_size(source, "Medium")

    def test_scale_missing_directory(self):
        with self.assertRaises(FileNotFoundError):
            self.converter.scale_grid_size(self.root / "nope", "Small")


class TestBinaryCacheLock(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _lock_binary_cache(self, calls: dict):
        real_unlink = Path.unlink

        def fake(path: Path, missing_ok: bool = False):
            if path.name.endswith("sbcB5"):
                calls["n"] += 1
                raise PermissionError("locked by game")
            return real_unlink(path, missing_ok=missing_ok)

        return fake

    def test_process_blueprint_fails_when_binary_cache_is_locked(self):
        source = write_blueprint_dir(
            self.root,
            "Ship",
            ["LargeBlockArmorBlock"],
            extra_files=["bp.sbcB5"],
        )
        replacer = ArmorBlockReplacer(include_profiles=False)
        calls = {"n": 0}
        with patch("se_armor_replacer.time.sleep", return_value=None):
            with patch.object(Path, "unlink", self._lock_binary_cache(calls)):
                with self.assertRaises(BinaryCacheError) as ctx:
                    replacer.process_blueprint(str(source), create_backup=False)
        self.assertEqual(calls["n"], 3)
        self.assertIn("stale binary", str(ctx.exception).lower())
        self.assertTrue((source / "bp.sbcB5").exists())

    def test_copy_fails_when_destination_binary_cache_is_locked(self):
        source = write_blueprint_dir(
            self.root,
            "Ship",
            ["LargeBlockArmorBlock"],
            extra_files=["bp.sbcB5"],
        )
        converter = BlueprintConverter(verbose=False, include_profiles=False)
        calls = {"n": 0}
        with patch("se_armor_replacer.time.sleep", return_value=None):
            with patch.object(Path, "unlink", self._lock_binary_cache(calls)):
                with self.assertRaises(BinaryCacheError) as ctx:
                    converter.create_converted_blueprint(source)
        self.assertEqual(calls["n"], 3)
        self.assertIn("stale binary", str(ctx.exception).lower())
        self.assertIsInstance(ctx.exception, BinaryCacheError)
        dest = self.root / "HEAVYARMOR_Ship"
        self.assertTrue(dest.exists())
        self.assertTrue((dest / "bp.sbcB5").exists())
        # Cache removal runs before the armor rewrite, so a lock does not
        # leave a heavy-armor bp.sbc next to the stale binary the game loads.
        copied = (dest / "bp.sbc").read_text(encoding="utf-8")
        self.assertIn("LargeBlockArmorBlock", copied)
        self.assertNotIn("LargeHeavyBlockArmorBlock", copied)

    def test_cli_returns_failure_when_binary_cache_is_locked(self):
        source = write_blueprint_dir(
            self.root,
            "Ship",
            ["LargeBlockArmorBlock"],
            extra_files=["bp.sbcB5"],
        )
        calls = {"n": 0}
        stderr = io.StringIO()
        with patch("se_armor_replacer.time.sleep", return_value=None):
            with patch.object(Path, "unlink", self._lock_binary_cache(calls)):
                with patch("sys.argv", ["se_armor_replacer", str(source), "--no-backup", "--no-profiles"]):
                    with redirect_stderr(stderr):
                        code = main()
        self.assertEqual(code, 1)
        self.assertEqual(calls["n"], 3)
        message = stderr.getvalue().lower()
        self.assertIn("binary cache", message)
        self.assertIn("stale binary", message)
        self.assertNotIn("success", message)


if __name__ == "__main__":
    unittest.main()
