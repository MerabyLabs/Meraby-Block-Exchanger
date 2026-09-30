# MBX review — 2026-09-30

Review of Meraby Block Exchanger 3.2.3 (`main` at the time of the pass). No new public release was tagged. No Stripe checkout was added. No Keen affiliation is claimed. A paid commercial license stays unoffered until Keen Software House gives written permission.

Draft fixes:

- Parse / GUI copy safety: https://github.com/MerabyLabs/Meraby-Block-Exchanger/pull/39
- Windows launch, honesty wording, packaging: this branch

## P0

None that should ship as a hotfix release by themselves.

The closest data-loss case was analytics **Apply fix**, which wrote the selected `bp.sbc` in place (and left `bp.sbcB5` in place, so the game could ignore the edit). The dialog did say the original would be edited, which contradicts the README rule that the GUI always writes a new copy. That path is changed in PR 39. It is not a silent overwrite.

## P1

| Finding | Where | Status |
|---|---|---|
| Readers only counted `MyObjectBuilder_CubeBlock`. Concrete tags such as `MyObjectBuilder_Cockpit` and `MyObjectBuilder_Thrust` were invisible to the scanner, analytics, armor hardening, the skin pass, hierarchy counts, and the 2D map, while conversion still rewrote them. A health audit could say "no cockpit" and then edit the ship. | `blueprint_scanner.py`, `blueprint_analytics.py`, `mappings/armor_hardening.py`, `mappings/skin_palette_engine.py`, `subgrid_engine/hierarchy_parser.py`, `subgrid_engine/visualizer_matrix.py` | Fixed in PR 39. Shared walker: `safe_xml.iter_cube_blocks`. |
| A present `SubtypeName` could be overwritten because a different `SubtypeId` was in the armor map. Grid rescale copied the scaled `SubtypeName` onto a different `SubtypeId`. | `se_armor_replacer.py` `replace_blocks`, `blueprint_converter.py` `scale_grid_size` | Fixed in PR 39. |
| Analytics repair and armor hardening did not follow the GUI copy rule. Hardening also wrote only `bp.sbc`, dropping thumbnails, and did not sync the ship id to the new folder name. | `ui/app.py` `apply_health_fix`, `mappings/armor_hardening.py` | Fixed in PR 39. Copies are `REPAIRED_`, `_HARDENED`, and `_LIGHTWEIGHT`. |
| CLI `--profile-dir` defaulted to `profiles` in the current directory. `ProfileManager` created that folder and skipped the bundled profiles. | `se_armor_replacer.py` | Fixed here. Default is `resource_paths.bundled_profiles_dir()`. |
| `launch_gui.bat` did not `cd` to its own folder. `launch.bat` treated any `python` on PATH as good (including the Windows Store stub) and fell through to a hardcoded Python 3.13, which the README does not support. A failed double-click closed the window. | `launch.bat`, `launch_gui.bat` | Fixed here. Prefer `py -3.12`, then `py -3.11`, then `py -3`, then a `python` that can run `import sys`. Pause on failure. |
| A corrupt `%APPDATA%\SEBlockExchanger\settings.json`, or a broken `.sebx-profile`, aborted startup before the window existed. | `app_settings.py`, `mapping_profiles.py` `load_all` | Fixed here. Bad settings fall back to defaults. Bad profiles are skipped with a stderr warning. |
| Workshop discovery only probed a few `C:`–`G:` path shapes, so a library that exists only in `libraryfolders.vdf` was invisible and the importer told the user to download the item again. | `workshop_sync/steam_fetcher.py` | Fixed here. Existing path probes stay. VDF `path` entries are added when that workshop folder exists. |
| The SE2 tab said "Ready to share", "this is a vanilla build", and "ready to share on vanilla servers". The score is a keyword heuristic. Prosperity-style ids with none of the keywords do not lower it. The JSON export was already labeled `unverified_internal_placeholders`. | `ui/preview_panel.py`, `blueprint_analytics.py` `compute_se2_readiness` | Fixed here. The tab is a planning score and says it is not an SE2 load test and not a Keen result. |
| README and LICENSE invited a commercial license as if one could be bought. Paid sale is waiting on Keen written permission. | `README.md`, `LICENSE` section 2 | Fixed here. Personal use stays free. The text says a paid license is not for sale and the email is not a checkout. No Stripe, no price, no affiliation claim. |
| DLC / Prosperity pairs in `mappings/dlc_substitution.py` are hand-authored. A wrong target writes a subtype the game may drop. The 2026-09-28 gap note already says not to invent ids. | `mappings/dlc_substitution.py`, `docs/rnd-mbx-current-se-gap-2026-09-28.md` | Not changed. Do not add or "correct" pairs until a cubeblock export from the client Matthew will use. A wrong swap is worse than a missing pair. |
| `SE1_TO_SE2_TRANSLATION_TABLE` targets are internal `VR3_*` placeholders (26 entries), not Keen Space Engineers 2 ids. | `engine_compat.py` | Already labeled in the JSON payload. Do not replace them with guessed ids. |

## P2

| Finding | Where | Status |
|---|---|---|
| `__build_date__ = date.today()` so the footer date changed every calendar day and looked like a new build. | `version.py`, `ui/footer.py` | Fixed here. Stamp is the v3.2.3 release date `2026-09-29`, shown as "released". Bump it in the same commit as `__version__` on the next release. |
| The release workflow built and published an exe without running pytest. PyInstaller UPX default can differ between the spec (`upx=True`) and a runner that happens to have UPX on PATH. | `.github/workflows/release.yml`, `Meraby_Block_Exchanger.spec`, `build_exe.bat` | Fixed here for the next tag. Workflow runs `pytest -q` before PyInstaller and passes `--noupx`. Spec sets `upx=False`. No tag was pushed. |
| CLI still overwrites `bp.sbc` in place unless `-o` or `--dry-run`. A `.sbc.backup` is the default. | `se_armor_replacer.py`, README | Documented. Left as the CLI contract. |
| `shutil.copytree` follows symlink contents. Workshop import refuses junctions; convert/stage does not. | `blueprint_converter.py` `copy_blueprint_folder` | Not changed. A junction inside a blueprint folder can still be copied as file content. |
| Mod.io zip extract has no uncompressed-size cap. Profile import from a URL has no byte cap. | `workshop_sync/modio_fetcher.py`, `mapping_profiles.py` `import_profile` | Not changed. Both run only after the user picks a file or pastes a URL. |
| PB Doctor denylist is broader than the public whitelist notes, and those notes are older than 1.210. `System.Environment` is stored as a namespace. | `pb_doctor/whitelist_rules.py` | Not changed. Do not edit it from the wiki. Wait for an IlChecker dump from the same build as the cubeblock export. |
| `data/block_costs.json` covers 48 subtypes. Analytics cost totals are comparative. | `data/block_costs.json` | Not filled in. The file already says the numbers are not an engineering simulation. |
| CI runs on Ubuntu only. This pass did not launch the CustomTkinter window or a Windows exe. | `.github/workflows/ci.yml` | Tests and mypy were run on Linux. Shortcut, drag-drop, and the packaged exe were not executed here. |
| Release workflow still shells out to PyInstaller flags instead of `Meraby_Block_Exchanger.spec`. The datas lists match today; they can drift again. | `release.yml`, `Meraby_Block_Exchanger.spec` | Noted. `--noupx` is now on both paths. |

## Release steps (do not tag from this review)

1. Merge the drafts you want.
2. Bump `version.py` `__version__` and `__build_date__` together. Add a `## vX.Y.Z` section to `RELEASE_NOTES.md`. Do not leave `__build_date__` as `date.today()`.
3. Push tag `vX.Y.Z`. `.github/workflows/release.yml` checks the tag against `version.py`, runs pytest, builds `Meraby_Block_Exchanger_vX.Y.Z.exe` with `--noupx`, and publishes `SHA256SUMS.txt` plus the `.sha256` sidecar.
4. Do not republish a v3.2.0 exe. Confirm the asset name is `Meraby_Block_Exchanger_vX.Y.Z.exe`.
5. Do not add a price, Stripe, or "official Keen" wording to the release body. The workflow already prepends the non-affiliation line.
