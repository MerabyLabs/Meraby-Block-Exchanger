"""Player-facing SE2 estimate and convert copy.

These tests lock behavior that does not require a new subtype ID.
"""

from __future__ import annotations

import pytest

from blueprint_analytics import (
    DLC_KEYWORDS,
    compute_se2_readiness,
    format_se2_readiness_lines,
)
from ui.labels import (
    armor_change_message,
    convert_confirm_body,
    copy_created_message,
    library_empty_copy,
    nothing_to_convert_message,
    pending_change_message,
    se2_export_confirm_message,
)

CATALOG_DLC_WITHOUT_KEYWORDS = (
    "ProsperityCockpit",
    "LargeBatteryBank",
    "FactoryStairs",
    "ContactRadarAntenna",
    "SignalBeacon",
)


@pytest.mark.parametrize("subtype", CATALOG_DLC_WITHOUT_KEYWORDS)
def test_catalog_dlc_without_keyword_lowers_the_estimate(subtype: str):
    lowered = subtype.lower()
    assert not any(keyword in lowered for keyword in DLC_KEYWORDS)

    readiness = compute_se2_readiness({subtype: 2, "LargeBlockArmorBlock": 10})
    assert readiness.dlc_count == 2
    assert subtype in readiness.dlc_subtypes
    assert readiness.score == 90
    assert readiness.status == "OPTIMAL"


def test_dlc_keyword_and_catalog_entry_count_once():
    readiness = compute_se2_readiness({"LargeBlockSmallThrustSciFi": 3})
    assert readiness.dlc_count == 3
    assert readiness.dlc_subtypes == ("LargeBlockSmallThrustSciFi",)


def test_connector_is_noted_and_does_not_change_the_score():
    plain = compute_se2_readiness({"LargeBlockArmorBlock": 4})
    with_connector = compute_se2_readiness({"LargeBlockArmorBlock": 4, "Connector": 3})
    assert plain.score == with_connector.score == 100
    assert plain.connector_count == 0
    assert with_connector.connector_count == 3
    assert with_connector.subgrid_count == 0


def test_rotor_still_lowers_the_estimate():
    readiness = compute_se2_readiness({"LargeRotor": 1})
    assert readiness.subgrid_count == 1
    assert readiness.score == 85


def test_estimate_floors_at_twenty():
    readiness = compute_se2_readiness(
        {
            "LargeRotor": 10,
            "LargeProgrammableBlock": 10,
            "ProsperityCockpit": 10,
        }
    )
    assert readiness.score == 20
    assert readiness.status == "FRAGILE"


def test_readiness_notes_stay_a_planning_estimate():
    readiness = compute_se2_readiness(
        {
            "ProsperityCockpit": 1,
            "Connector": 2,
            "LargeRotor": 1,
        }
    )
    text = "\n".join(
        format_se2_readiness_lines(
            readiness,
            display_name="Hauler",
            grid_size="Large",
            block_count=4,
        )
    )
    assert "ProsperityCockpit" in text
    assert "planning estimate" in text
    assert "does not mean the ship will load" in text
    assert "SE1GridsToImport" in text
    assert "Grid Exporter" in text
    assert "not Keen block IDs" in text
    assert "ready to share" not in text.lower()
    assert "only the main grid" in text
    assert "subtype IDs were never published" in text


def test_nothing_to_convert_names_the_checked_categories():
    text = nothing_to_convert_message(["armor", "dlc_substitution"])
    assert "Armor" in text
    assert "DLC → vanilla" in text
    assert "does not overwrite the original" in text
    assert "no verified swap" in text


def test_pending_and_armor_messages_state_the_copy_outcome():
    pending = pending_change_message(4, ["thrusters"])
    assert pending.startswith("4 blocks will be rewritten")
    assert "not overwritten" in pending

    empty = pending_change_message(0, ["prototech"])
    assert "Prototech" in empty
    assert "will not change this ship" in empty

    armor = armor_change_message(ready=3, armor_ready=3, reverse=False, category_ids=["armor"])
    assert "heavy armor" in armor
    assert "not overwritten" in armor


def test_confirm_and_result_copy_keep_the_original():
    confirm = convert_confirm_body(
        display_name="Miner",
        count=1,
        target="heavy armor",
        category_text="Armor",
    )
    assert "new copy" in confirm
    assert "not changed" in confirm
    assert "stay as they are" in confirm

    created = copy_created_message("HEAVYARMOR_Miner", 20, 5)
    assert "5 of 20" in created
    assert "15 were left as they are" in created
    assert "not overwritten" in created

    untouched = copy_created_message("HEAVYARMOR_Miner", 20, 0)
    assert "copy matches the original" in untouched

    planning = copy_created_message("SE2_Miner", 8, 2, kind="se2")
    assert "not a Space Engineers 2 blueprint" in planning
    assert "placeholder" in planning

    export_prompt = se2_export_confirm_message("Miner")
    assert "SE1GridsToImport" in export_prompt
    assert "/export" in export_prompt
    assert "not changed" in export_prompt


def test_empty_library_copy_distinguishes_search_from_a_missing_folder():
    missing_title, missing_body = library_empty_copy("missing")
    assert "not found" in missing_title.lower()
    assert "Blueprints" in missing_body
    assert "new copy" in missing_body

    search_title, search_body = library_empty_copy("search")
    assert "search" in search_title.lower()
    assert "Clear the search" in search_body
    assert "Blueprints" not in search_body

    empty_title, empty_body = library_empty_copy("empty")
    assert "No ships" in empty_title
    assert "bp.sbc" in empty_body
    assert "does not overwrite" in empty_body
