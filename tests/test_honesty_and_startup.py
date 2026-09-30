"""Honesty wording and startup guards that should not depend on a Windows desktop."""

from __future__ import annotations

from pathlib import Path

from app_settings import SettingsStore
from blueprint_analytics import SE2_SCORE_NOTE, SE2_STATUS_TITLES, compute_se2_readiness, format_se2_notes
from mapping_profiles import ProfileManager
from resource_paths import bundled_profiles_dir
from se_armor_replacer import resolve_profile_dir
from version import __build_date__, __version__
from workshop_sync.steam_fetcher import SteamWorkshopFetcher

ROOT = Path(__file__).resolve().parents[1]


def test_build_date_is_the_release_stamp():
    assert __version__ == "3.2.3"
    assert __build_date__ == "2026-09-29"
    assert "date.today" not in (ROOT / "version.py").read_text(encoding="utf-8")


def test_se2_notes_do_not_claim_a_load_or_a_vanilla_clearance():
    readiness = compute_se2_readiness({"LargeBlockArmorBlock": 4})
    notes = format_se2_notes("Hauler", "Large", 4, readiness)
    assert "not a Space Engineers 2 load test" in notes
    assert "not a vanilla-server clearance" in notes
    assert "Ready to share" not in notes
    assert "this is a vanilla build" not in notes
    assert "Keen Software House" in SE2_SCORE_NOTE
    assert "Ready to share" not in " ".join(SE2_STATUS_TITLES.values())


def test_commercial_license_is_not_offered_for_sale():
    license_text = (ROOT / "LICENSE").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "not currently offered for sale" in license_text
    assert "not a checkout" in license_text
    assert "Stripe" not in license_text
    assert "not currently for sale" in readme
    assert "Not affiliated with or endorsed by Keen Software House" in readme


def test_profile_dir_default_is_bundled_not_the_working_directory():
    assert resolve_profile_dir(None) == bundled_profiles_dir()
    assert resolve_profile_dir("   ") == bundled_profiles_dir()
    assert resolve_profile_dir("custom") == Path("custom")


def test_corrupt_settings_do_not_raise(tmp_path: Path):
    path = tmp_path / "settings.json"
    path.write_text("{", encoding="utf-8")
    settings = SettingsStore(path).load()
    assert settings.enabled_categories == ["armor"]
    path.write_text('{"cache_hours": "nope"}', encoding="utf-8")
    assert SettingsStore(path).load().cache_hours == 24


def test_broken_profile_is_skipped(tmp_path: Path):
    good = tmp_path / "ok.sebx-profile"
    good.write_text((ROOT / "profiles" / "build_vision.sebx-profile").read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "bad.sebx-profile").write_text("{", encoding="utf-8")
    loaded = ProfileManager(tmp_path).load_all()
    assert [profile.name for profile in loaded] == ["Build Vision Enhancements"]


def test_steam_library_vdf_paths_unescape():
    text = '"path"\t\t"D:\\\\Games\\\\Steam"\n"path" "C:\\\\Program Files (x86)\\\\Steam"\n'
    roots = [str(path) for path in SteamWorkshopFetcher.library_folders_from_vdf(text)]
    assert r"D:\Games\Steam" in roots
    assert r"C:\Program Files (x86)\Steam" in roots


def test_windows_launchers_pin_directory_and_supported_python():
    launch = (ROOT / "launch.bat").read_text(encoding="utf-8")
    gui = (ROOT / "launch_gui.bat").read_text(encoding="utf-8")
    for text in (launch, gui):
        assert 'cd /d "%~dp0"' in text
        assert "py -3.12" in text
        assert "py -3.11" in text
        assert "Python313" not in text
