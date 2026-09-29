# MBX current-SE gap inventory — 2026-09-28

**Author:** Nora Vale (R&D) · **Track:** Alex FOUNDER TRACK, Mon inventory  
**Product:** Meraby Block Exchanger (MBX), baseline ship **v3.2.1** (2026-08-29)  
**Repo:** `MerabyLabs/Meraby-Block-Exchanger` · branch `cursor/mbx-current-se-gap-d7b6`  
**Public title:** Meraby Block Exchanger (MBX). This note does not change product chrome.

This is an inventory of what **this repository** encodes today, plus the export needed before any block table is refreshed. It is not a claim that the tables match a current Space Engineers install. No `CubeBlocks*.sbc` (or `SpaceEngineers.exe`) was present on the machine that produced this note. No new DLC or vanilla subtype pairs were added.

Staff review of this note is not Matthew’s sale review. Nothing here is sale-ready.

## Catalog the repo knows today

Subtypes are **hand-written Python dicts** and profile JSON. Nothing in-tree generates them from Keen content files. A pair is `source subtype string -> target subtype string`. `mappings/registry.py` rejects empty IDs, identity pairs, and circular swaps. Forward merges allow many sources to share one target. Reverse merges do not.

| Category | File | Pairs | Unique targets | Direction | Default | In `--all-categories` |
|---|---|---:|---:|---|---|---|
| armor | `mappings/armor.py` | 70 (35 large, 35 small) | 70 | light → heavy, injective | on | yes |
| thrusters | `mappings/thrusters.py` | 6 | 6 | small → large, injective | off | yes |
| weapons | `mappings/weapons.py` | 5 | 5 | tier-up, injective | off | yes |
| functional | `mappings/functional.py` | 6 | 6 | basic/small → large, injective | off | yes |
| dlc_substitution | `mappings/dlc_substitution.py` | 96 | 45 | many DLC IDs → one vanilla ID | off | yes |
| prototech | `mappings/prototech.py` (`VANILLA_TO_PROTOTECH_PAIRS`) | 23 | 23 | vanilla → Prototech, injective | off | **no** (`source="endgame"`) |
| prototech survival | `PROTOTECH_TO_VANILLA_PAIRS` via `get_survival_sanity_mapping()` | 36 | 23 | Prototech → vanilla, not a registry category | tool only | no |

`--all-categories` forward-merges the five `source="built-in"` categories into **183** pairs. Prototech stays opt-in because it reuses thruster, weapon, and functional sources (`LargeBlockSmallThrust`, `LargeGatlingTurret`, `LargeBlockSmallGenerator`, and others). Enabling prototech together with those categories raises `MappingValidationError`. A saved settings file that contains that collision now falls back to armor instead of failing GUI startup.

Release notes for v3.2.0 already say armor 70, DLC 96, Prototech 23. Those counts still match the code. The gap is freshness against the game, not an internal count drift since 3.2.0.

### How a subtype string gets into a blueprint

1. Built-in categories live in `mappings/*.py` and are registered by `build_registry()`.
2. Mod profiles (`profiles/*.sebx-profile`) are JSON `[source, target]` lists loaded by `mapping_profiles.py`. All three bundled profiles set `"game_version": "1.205+"`. That string is an author label. It is not a test result.
3. `ArmorBlockReplacer` / `BlueprintConverter` rewrite `SubtypeName` and `SubtypeId` when the current text is a mapping key. Unlisted subtypes are left unchanged (silent no-op).
4. The GUI copies the blueprint folder and writes the copy (`HEAVYARMOR_`, `CONVERTED_`, `SURVIVAL_READY_`, `PROTOTECH_`, and similar prefixes). CLI still overwrites in place unless `-o` or `--dry-run`.
5. Production writes go through `safe_xml.safe_write` (temp file, then replace).

### `data/block_costs.json`

- Metadata `version` **1.0**. Source text: “vanilla block/component approximations from in-game definitions and wiki data.” No game build, no date.
- **48** block entries. Category counts inside the file: thrusters 12, weapons 10, power 10, armor 4, production 4, storage 4, control 4.
- Component→ingot and ore-yield tables sit beside the block list and feed `blueprint_analytics.py` (PCU, mass, components, ingots, ores). The file itself says the numbers are comparative, not an engineering simulation.
- **294** subtype strings that appear in the mapping dicts above are absent from `blocks`. Armor costs cover 4 of the 140 light/heavy armor IDs. Almost every DLC source ID is absent.
- **6** cost IDs are not in any mapping: `LargeBlockRemoteControl`, `LargeBlockSolarPanel`, `LargeBlockWindTurbine`, `SmallBlockCockpit`, `SmallHydrogenEngine`, `SmallRemoteControl`.

### Bundled mod profiles (smoke only — do not expand)

| Profile | `game_version` label | Categories | Pairs | Target style |
|---|---|---:|---:|---|
| `profiles/weaponcore.sebx-profile` | 1.205+ | 2 | 5 | `WC_*` |
| `profiles/assertive_armaments.sebx-profile` | 1.205+ | 2 | 5 | `AA_*` |
| `profiles/build_vision.sebx-profile` | 1.205+ | 1 | 4 | `BV_*` |

Same-source overlaps (for example `SmallGatlingGun` in WeaponCore and Assertive) are why profiles stay out of `--all-categories`.

### PB Doctor

| Piece | Where | What it encodes |
|---|---|---|
| Denylist | `pb_doctor/whitelist_rules.py` `FORBIDDEN_NAMESPACES` | 14 names: `System.IO`, `System.Threading`, `System.Reflection`, `System.Net`, `System.Net.Sockets`, `System.Diagnostics`, `System.Runtime`, `System.Runtime.InteropServices`, `System.Security`, `System.Timers`, `System.Environment`, `System.AppDomain`, `System.Management`, `Microsoft.Win32` |
| Allow list | `ALLOWED_INGAME_NAMESPACES` | 11 names. Exported. **Not enforced.** The validator only flags the denylist and a few keyword patterns. |
| Limits | same file | 100,000 character error, 80,000 warning, instruction heuristic warning at 35,000 and “limit” at 49,500 |
| Keyword bans | `FORBIDDEN_PATTERNS` | `namespace`, `async`, `await`, `dynamic`, `goto`, `Thread`, unicode ellipsis |
| Fixer | `pb_doctor/script_fixer.py` | Strips forbidden `using` lines (including `using static`, aliases, `global::`). Does not rewrite inline type references. |

There is no build stamp on the whitelist. `System.Environment` and `System.AppDomain` are types, not namespaces; they are still stored in the namespace denylist.

### SE2 score and export

- `blueprint_analytics.compute_se2_readiness` is a keyword score. DLC keywords: `scifi`, `industrial`, `wasteland`, `warfare`, `reskin`, `decorative`, `desert`, `cab`, `buggy`, `sparks`, `vending`, `storeblock`. Scripts match `programmable`. Subgrids match `rotor`, `stator`, `hinge`, `piston`. Score starts at 100, floors at 20, labels OPTIMAL / STABLE / COMPLEX / FRAGILE.
- Several IDs in the Prosperity section of `dlc_substitution.py` (`ProsperityCockpit`, `LargeBatteryBank`, `FactoryStairs`, `ContactRadarAntenna`, `SignalBeacon`) contain none of those keywords, so they would not lower the score.
- `engine_compat.SE1_TO_SE2_TRANSLATION_TABLE` has **26** entries. Targets are `VR3_*` strings. Unknown blocks are emitted as `VR3_Legacy_{subtype}`. The JSON this branch writes now sets `translation_status` to `unverified_internal_placeholders` and states that those names are not Keen Space Engineers 2 block IDs.

### Last SE-version claim in the notes

There is no `CHANGELOG` file. `RELEASE_NOTES.md` is the log.

- **v3.2.1 (2026-08-29)** — portable exe path, AppData profiles, Win64 drag-drop, Selective Exchange font. No Space Engineers build ID.
- **v3.2.0 (2026-08-29)** — product surface, including the 70 / 96 / 23 pair counts. No build ID.
- The only in-repo “game version” strings are the profile label and UI default **`1.205+`** (`profiles/README.md`, each bundled profile, `ui/profile_editor.py`, `.github/ISSUE_TEMPLATE/bug_report.yml`).

v3.2.1’s date is after Keen’s public Prosperity announcement. The notes do not say the tables were regenerated for that update.

## Public Keen pages read for this inventory

Fetched 2026-09-28. These are announcements and a community wiki, not an extract of the client.

- Keen support, Update 1.210 Prosperity: <https://support.keenswh.com/spaceengineers/pc/announcement/update-1-210-prosperity>
- Prosperity pack page: <https://www.spaceengineersgame.com/prosperity/>
- Programmable-block whitelist overview, **last checked for Space Engineers v1.208.014** (the page’s own stamp, older than 1.210): <https://spaceengineers.wiki.gg/wiki/Scripting/Whitelist_Overview>

The 1.210 announcement’s **new base-game blocks**, by display name only: Prototech O2/H2 Generator (1×L), Flat Collector (1×S), Structural Platform Conveyor (1×L), Short Stairs (1×L), Passage 2 Frame (1×L). Decorative Pack 2 gains triangular grated catwalks (2×L). The announcement points modders at `Cubeblocks_Prototech.sbc`.

The Prosperity Pack is described as 50+ decorative blocks: sloped cockpits (2×S + 2×L), bulky hydrogen tank (1×S + 1×L), steep stairs (6×L), solid stairs (8×L), battery bank (1×S + 2×L), square railings (13×L), decorative server racks (3×L), cable run (7×L), round and square lights. No subtype IDs are published there.

A secondary writeup dates hotfix **1.210.014** to 2026-08-14 and, as of that writeup’s 2026-09-05 check, treated it as the newest hotfix it had confirmed. This inventory did **not** query Steam. The live build ID is still a Matthew export item.

## BLOCKERS — Matthew SE install export

Do not commit Keen’s `Content` files to this repo. Copy them to a local ops drop Alex can hand to R&D.

1. **Build ID** from the client Matthew will use for the Thu/Fri in-game pass (the About/version string, not a wiki “last checked” line). Say whether it is still a 1.210.x build or something newer.
2. **Owned DLC list** on that same install, including whether Prosperity Pack is owned. Free update blocks and paid pack blocks need to be separated.
3. **Cubeblock definitions** from that install’s `Content` data: the files matching `CubeBlocks*.sbc` / `Cubeblocks*.sbc`, including the prototech file the 1.210 notes name (`Cubeblocks_Prototech.sbc`) and the DLC definition SBC files that ship subtypes. R&D needs `TypeId` + `SubtypeId` (and display name), not a screenshot of the G-menu.
4. **Cost refresh inputs**, only if Tue/Wed reaches analytics: component counts, PCU, and mass from those definitions (or `Components.sbc` plus the cubeblock component lists). Do not hand-edit `block_costs.json` from the wiki.
5. **PB whitelist from that build.** MDK2 pointed at this install, or an IlChecker dump (`MySandboxGame.InitIlChecker` / `MySpaceGameDefaultIlChecker`). The 1.208.014 wiki is not the authority for a 1.210 client.
6. **Three local blueprints** for the box matrix after the tables change: one small vanilla grid, one large vanilla grid, one ship that actually contains Prosperity and/or Prototech blocks from this install. GUI must keep writing a new folder.

Until those six exist, do not add subtype pairs and do not write “synced to SE 1.210” anywhere.

## Hypotheses (not measured on a client)

1. **Prosperity section IDs are guesses.** `dlc_substitution.py` labels 19 pairs as “PROSPERITY PACK (2026)” (`LargeSlopedCockpit`, `ProsperityDesk`, `FactoryStairs`, `ConduitConveyor`, `IndustrialWalkway`, and the rest of that block). The public pack list is sloped cockpits, bulky tanks, steep/solid stairs, battery banks, square railings, server racks, cable runs, and lights. Several repo IDs do not correspond to those families, and the families that are listed have no subtype IDs in the announcement. Treat the whole section as unverified until the cubeblock export lands.
2. **Contact, Signal, and several Warfare/Decorative source IDs are hand-authored the same way.** Examples: `ContactRadarAntenna`, `SignalBeacon`, `GatlingTurretReskin`, `StoreBlockSingle`. Some *targets* (`LargeBlockCockpit`, `LargeAssembler`, `LargeBlockSmallThrust`) also appear elsewhere in this repo, which only shows internal consistency.
3. **1.210 base-game additions are missing or only aliased.** Flat Collector, Structural Platform Conveyor, Short Stairs, Passage 2 Frame, and Decorative Pack 2 triangular catwalks do not appear as keys in the mapping dicts. Survival sanity already maps `LargePrototechO2H2` and `PrototechO2H2` to `LargeOxygenGenerator`. Whether the new Prototech O2/H2 Generator uses either of those IDs is unknown. If it does not, Upgrade to Prototech and Survival Sanity will no-op on it.
4. **PB denylist is coarser than the 1.208.014 wiki, and that wiki is already behind 1.210.** The fetched whitelist overview allows specific members under prefixes MBX bans outright: `System.Environment` (`NewLine`, `ProcessorCount`, `CurrentManagedThreadId`), parts of `System.IO` (`Path`, `BinaryReader`, `BinaryWriter`, `FileNotFoundException`), `System.Reflection.MemberInfo`, and `System.Runtime.CompilerServices.RuntimeHelpers`. The wrapper `using` list also includes namespaces absent from `ALLOWED_INGAME_NAMESPACES` (`System.Collections`, `System.Collections.Immutable`, `VRage`, `VRage.Game`, `VRage.Collections`, `Sandbox.Game.EntityComponents`, `SpaceEngineers.Game.ModAPI.Ingame`, `VRage.Scripting.MemorySafeTypes`, and others). Because the allow list is not enforced, the practical risk is false denylist hits and missed bans. Do not edit the denylist from the wiki alone.
5. **Keyword bans (`async`, `await`, `goto`, `dynamic`, `Thread`) are house rules** relative to that wiki page, which does not list them. Leave them until the IlChecker dump says otherwise.
6. **The 100,000-character and ~50,000-instruction figures are unstamped constants.** They may still match a common server default. They were not read from Matthew’s build.
7. **SE2 export and the readiness score are planning heuristics.** `VR3_*` names were not taken from a Space Engineers 2 catalog. The score is not a measured SE2 load.

## Fixes already on this branch (no new Keen IDs)

These are repo-internal defects found while counting the tables.

| Defect | What the code did | What it does now |
|---|---|---|
| `--all-categories --reverse` | Raised `MappingValidationError` (`LargeAssembler` reversed to both `BasicAssembler` and `LargeIndustrialAssembler`, plus thruster collisions) | One-way categories (duplicate targets) are skipped on reverse. DLC-only `--reverse` errors with an explicit message. CLI prints the skip. Forward DLC substitution is unchanged. |
| GUI direction toggle | `BlueprintScanner.set_reverse` used the same merge, so Heavy → Light could throw out of the Tk callback when DLC was combined with functional or thrusters | Reverse merge skips one-way categories. A merge error rolls the toggle back and toasts. A saved category set that cannot merge forward falls back to armor. |
| Selective Exchange suggestions | String edits and hardcoded names such as `SmallPrototechGyro`, `LargeBlockLargePrototechThrust`, and `IndustrialCockpit` → `Cockpit` (the table’s target is `LargeBlockCockpit`) | Suggestions come only from registered pairs (both directions when injective) plus the authored survival-sanity map. |
| PB Doctor entry points | `void Main` / `Program()` inside a comment or string counted as a real entry point, so the fixer did not insert `Main` | Entry-point scan and the instruction heuristic use `mask_csharp_non_code`, same as braces and forbidden-token scans. |
| SE2 JSON | Looked like an engine export while using placeholder subtype names | Payload carries `translation_status: unverified_internal_placeholders`. |

Tests: `tests/test_inventory_invariants.py` (catalog counts, reverse skip, PB comment/string, suggestion closure, SE2 label). CI (`.github/workflows/ci.yml`) now runs `pytest -q tests` on 3.11 and 3.12 beside the existing ruff/mypy/import smoke. v3.2.0 notes said the public tree shipped without a test suite; this branch puts back a small invariant suite so these fixes stay pinned. Pair counts are locked to the v3.2.1 tables on purpose — changing them is a later, export-backed edit.

Local run on this branch: `pytest -q tests` — 8 passed; `ruff check . --select F,E9` clean; mypy on the CI file list clean.

## Proposed upgrade order (Tue–Wed)

1. **Take the Matthew export** (blockers above). Freeze the build ID and DLC list in the next note before editing pairs.
2. **Diff subtype IDs**, in this order: Prosperity Pack and other 1.210 additions, then Prototech (including the new O2/H2 generator), then DLC packs whose source IDs fail the diff, then armor shapes the armor file comments label “Decorative / Warfare” (the category description still says vanilla — resolve that from the file, not from the comment). Missing IDs get listed. They do not get invented stand-ins.
3. **Silent no-ops and bad swaps first.** A wrong target that writes a subtype the client will drop is worse than a missing pair that leaves the block alone.
4. **Keep write safety as it is** unless a test shows otherwise: GUI new folder, `safe_xml.safe_write`, refuse unsafe zips. Re-run the reverse merge tests after any new injective category.
5. **PB Doctor** only after the IlChecker/MDK2 dump from the same build. Likely edit is the denylist’s broad prefixes, not a rewritten allow-list from the 1.208 wiki.
6. **`block_costs.json`** only where the export disagrees on components, PCU, or mass. Leave the other 294 holes as unknown rather than filling them with approximations.
7. **SE2** stays labeled speculative. Do not replace `VR3_*` with guessed Keen IDs.
8. **Strings / README title** stay on Jordan’s rename branch.

Wed–Thu box matrix and Thu/Fri in-game proof stay on the founder plan. They start after step 2 has a real ID list, not before.

## Out of scope

No Stripe, no price, no sell rail, no Keen permission email, no “official Keen” wording, no public rename.
