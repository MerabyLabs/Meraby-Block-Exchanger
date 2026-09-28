"""Round-trip tests for SE2MigrationBridge."""

from __future__ import annotations

import json
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from engine_compat import SE2MigrationBridge

_XSI_TYPE = "{http://www.w3.org/2001/XMLSchema-instance}type"


def _write_se1(folder: Path, blocks_xml: str) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    xml = f"""<?xml version="1.0"?>
<Definitions xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema">
  <ShipBlueprints>
    <ShipBlueprint xsi:type="MyObjectBuilder_ShipBlueprintDefinition">
      <Id Type="MyObjectBuilder_ShipBlueprintDefinition" Subtype="{folder.name}" />
      <CubeGrids>
        <CubeGrid>
          <GridSizeEnum>Large</GridSizeEnum>
          <CubeBlocks>
            {blocks_xml}
          </CubeBlocks>
        </CubeGrid>
      </CubeGrids>
    </ShipBlueprint>
  </ShipBlueprints>
</Definitions>
"""
    (folder / "bp.sbc").write_text(xml, encoding="utf-8")
    return folder


def _block_by_subtype(root: ET.Element, subtype: str) -> ET.Element:
    for block in root.findall(".//CubeBlocks/*"):
        if block.findtext("SubtypeName") == subtype:
            return block
    raise AssertionError(f"missing block {subtype}")


class TestSE2MigrationRoundTrip(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_round_trip_preserves_builder_orientation_and_entity_id(self):
        source = _write_se1(
            self.root / "Functional",
            """
            <MyObjectBuilder_CubeBlock xsi:type="MyObjectBuilder_Thrust">
              <SubtypeName>LargeBlockLargeThrust</SubtypeName>
              <EntityId>4242</EntityId>
              <BlockOrientation Forward="Left" Up="Down" />
              <Min x="1" y="2" z="3" />
            </MyObjectBuilder_CubeBlock>
            <MyObjectBuilder_CubeBlock xsi:type="MyObjectBuilder_Cockpit">
              <SubtypeName>LargeBlockCockpit</SubtypeName>
              <EntityId>99</EntityId>
              <BlockOrientation Forward="Up" Up="Backward" />
              <Min x="0" y="0" z="0" />
            </MyObjectBuilder_CubeBlock>
            <MyObjectBuilder_CubeBlock xsi:type="MyObjectBuilder_CubeBlock">
              <SubtypeName>ModdedRoundArmor</SubtypeName>
              <Min x="4" y="0" z="0" />
            </MyObjectBuilder_CubeBlock>
            """,
        )
        se2_dir, scanned, converted = SE2MigrationBridge.migrate_se1_to_se2(
            source, output_dir=self.root / "SE2_Functional"
        )
        self.assertEqual(scanned, 3)
        self.assertEqual(converted, 2)

        payload = json.loads((se2_dir / "blueprint.json").read_text(encoding="utf-8"))
        raw = json.dumps(payload)
        self.assertNotIn("VR3_Legacy_", raw)
        blocks = payload["grids"][0]["blocks"]
        by_original = {block["original_se1_subtype"]: block for block in blocks}

        thrust = by_original["LargeBlockLargeThrust"]
        self.assertEqual(thrust["subtype"], "VR3_Large_IonThrust_Large")
        self.assertTrue(thrust["se2_mapped"])
        self.assertFalse(thrust["passthrough"])
        self.assertEqual(thrust["original_se1_builder_type"], "MyObjectBuilder_Thrust")
        self.assertEqual(thrust["original_se1_entity_id"], "4242")
        self.assertEqual(thrust["orientation"], {"forward": "Left", "up": "Down"})

        cockpit = by_original["LargeBlockCockpit"]
        self.assertEqual(cockpit["original_se1_builder_type"], "MyObjectBuilder_Cockpit")
        self.assertEqual(cockpit["orientation"]["forward"], "Up")
        self.assertEqual(cockpit["orientation"]["up"], "Backward")

        unmapped = by_original["ModdedRoundArmor"]
        self.assertEqual(unmapped["subtype"], "ModdedRoundArmor")
        self.assertTrue(unmapped["passthrough"])
        self.assertFalse(unmapped["se2_mapped"])
        self.assertNotIn("orientation", unmapped)
        self.assertFalse(str(unmapped["subtype"]).startswith("VR3_"))

        se1_dir, back_scanned, back_converted = SE2MigrationBridge.migrate_se2_to_se1(
            se2_dir, output_dir=self.root / "SE1_Functional"
        )
        self.assertEqual(back_scanned, 3)
        self.assertEqual(back_converted, 2)
        restored = ET.parse(se1_dir / "bp.sbc").getroot()

        thrust_block = _block_by_subtype(restored, "LargeBlockLargeThrust")
        self.assertEqual(thrust_block.get(_XSI_TYPE), "MyObjectBuilder_Thrust")
        self.assertNotEqual(thrust_block.get(_XSI_TYPE), "MyObjectBuilder_CubeBlock")
        self.assertEqual(thrust_block.findtext("EntityId"), "4242")
        orient = thrust_block.find("BlockOrientation")
        self.assertIsNotNone(orient)
        assert orient is not None
        self.assertEqual(orient.attrib["Forward"], "Left")
        self.assertEqual(orient.attrib["Up"], "Down")
        min_elem = thrust_block.find("Min")
        self.assertIsNotNone(min_elem)
        assert min_elem is not None
        self.assertEqual((min_elem.attrib["x"], min_elem.attrib["y"], min_elem.attrib["z"]), ("1", "2", "3"))

        cockpit_block = _block_by_subtype(restored, "LargeBlockCockpit")
        self.assertEqual(cockpit_block.get(_XSI_TYPE), "MyObjectBuilder_Cockpit")
        cockpit_orient = cockpit_block.find("BlockOrientation")
        self.assertIsNotNone(cockpit_orient)
        assert cockpit_orient is not None
        self.assertEqual(cockpit_orient.attrib["Forward"], "Up")
        self.assertEqual(cockpit_orient.attrib["Up"], "Backward")
        self.assertEqual(cockpit_block.findtext("EntityId"), "99")

        modded = _block_by_subtype(restored, "ModdedRoundArmor")
        self.assertEqual(modded.get(_XSI_TYPE), "MyObjectBuilder_CubeBlock")
        self.assertIsNone(modded.find("BlockOrientation"))
        subtypes = [elem.text for elem in restored.findall(".//SubtypeName")]
        self.assertNotIn("LargeBlockArmorBlock", subtypes)

    def test_reverse_uses_subtype_builder_map_when_original_type_missing(self):
        payload = {
            "blueprint_name": "MappedOnly",
            "grids": [
                {
                    "name": "Grid",
                    "grid_size": "Large",
                    "blocks": [
                        {
                            "subtype": "VR3_Large_IonThrust_Large",
                            "position": {"x": 2, "y": 0, "z": 1},
                            "orientation": {"forward": "Forward", "up": "Left"},
                        }
                    ],
                }
            ],
        }
        se2_dir = self.root / "SE2_MappedOnly"
        se2_dir.mkdir()
        (se2_dir / "blueprint.json").write_text(json.dumps(payload), encoding="utf-8")
        se1_dir, scanned, converted = SE2MigrationBridge.migrate_se2_to_se1(
            se2_dir, output_dir=self.root / "SE1_MappedOnly"
        )
        self.assertEqual((scanned, converted), (1, 1))
        block = ET.parse(se1_dir / "bp.sbc").find(".//CubeBlocks/*")
        self.assertIsNotNone(block)
        assert block is not None
        self.assertEqual(block.findtext("SubtypeName"), "LargeBlockLargeThrust")
        self.assertEqual(block.get(_XSI_TYPE), "MyObjectBuilder_Thrust")
        orient = block.find("BlockOrientation")
        self.assertIsNotNone(orient)
        assert orient is not None
        self.assertEqual(orient.attrib["Forward"], "Forward")
        self.assertEqual(orient.attrib["Up"], "Left")

    def test_legacy_vr3_id_is_not_rewritten_as_armor(self):
        payload = {
            "blueprint_name": "Legacy",
            "grids": [
                {
                    "name": "Grid",
                    "grid_size": "Large",
                    "blocks": [
                        {"subtype": "VR3_Legacy_ModdedRoundArmor", "position": {"x": 0, "y": 0, "z": 0}},
                        {"subtype": "VR3_NotARealBlock", "position": {"x": 1, "y": 0, "z": 0}},
                    ],
                }
            ],
        }
        se2_dir = self.root / "SE2_Legacy"
        se2_dir.mkdir()
        (se2_dir / "blueprint.json").write_text(json.dumps(payload), encoding="utf-8")
        se1_dir, _, converted = SE2MigrationBridge.migrate_se2_to_se1(
            se2_dir, output_dir=self.root / "SE1_Legacy"
        )
        self.assertEqual(converted, 0)
        subtypes = [elem.text for elem in ET.parse(se1_dir / "bp.sbc").findall(".//SubtypeName")]
        self.assertEqual(subtypes, ["ModdedRoundArmor", "VR3_NotARealBlock"])
        self.assertNotIn("LargeBlockArmorBlock", subtypes)


if __name__ == "__main__":
    unittest.main()
