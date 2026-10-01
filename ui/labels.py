"""Human-readable labels for categories, modes, and conversion CTAs."""

from __future__ import annotations

# Built-in mapping keys → short, player-facing names
_CATEGORY_TITLES: dict[str, str] = {
    "armor": "Armor",
    "thrusters": "Thrusters",
    "gyros": "Gyroscopes",
    "reactors": "Reactors",
    "batteries": "Batteries",
    "cargo": "Cargo",
    "cockpits": "Cockpits",
    "doors": "Doors",
    "windows": "Windows",
    "lights": "Lights",
    "conveyor": "Conveyors",
    "functional": "Production & power",
    "weapons": "Weapons",
    "advanced": "Advanced blocks",
    "dlc_substitution": "DLC → vanilla",
    "prototech": "Prototech",
}

_CATEGORY_HINTS: dict[str, str] = {
    "armor": "Light ↔ heavy plates",
    "thrusters": "Small → large (and reverse)",
    "gyros": "Small → large",
    "reactors": "Small → large",
    "batteries": "Small → large",
    "cargo": "Small → large containers",
    "cockpits": "Fighter / industrial seats",
    "doors": "Sliding / airtight doors",
    "windows": "Window variants",
    "lights": "Interior / spotlight",
    "conveyor": "Tubes and junctions",
    "functional": "Refineries, assemblers, generators",
    "weapons": "Gatlings, missiles, interiors",
    "advanced": "Less common block swaps",
    "dlc_substitution": "Paid DLC blocks → free equivalents",
    "prototech": "Vanilla ↔ Factorum Prototech",
}

# Scan / convert group headers used by ControlPanel
CATEGORY_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Core", ("armor", "thrusters", "gyros", "reactors", "batteries")),
    ("Ship systems", ("cargo", "cockpits", "doors", "windows", "lights", "conveyor")),
    ("Combat & extra", ("functional", "weapons", "advanced", "dlc_substitution", "prototech")),
)


def category_label(category_id: str) -> str:
    """Return a sentence-case label for a mapping or profile category id."""
    if not category_id:
        return ""
    known = _CATEGORY_TITLES.get(category_id)
    if known:
        return known
    if category_id.startswith("profile:"):
        rest = category_id[len("profile:") :]
        parts = [p.strip() for p in rest.split(":") if p.strip()]
        pretty = " · ".join(_title_words(p) for p in parts)
        return pretty or category_id
    return _title_words(category_id.replace("_", " "))


def category_hint(category_id: str) -> str:
    """One-line hint shown next to a category checkbox."""
    return _CATEGORY_HINTS.get(category_id, "")


def _title_words(text: str) -> str:
    return " ".join(word.capitalize() for word in text.replace("_", " ").replace("-", " ").split())


def grouped_category_ids(all_ids: list[str]) -> list[tuple[str, list[str]]]:
    """Partition category ids into named groups; leftover ids go under Profiles."""
    remaining = list(all_ids)
    groups: list[tuple[str, list[str]]] = []
    for title, members in CATEGORY_GROUPS:
        present = [m for m in members if m in remaining]
        if present:
            groups.append((title, present))
            for m in present:
                remaining.remove(m)
    if remaining:
        groups.append(("Installed profiles", remaining))
    return groups


def conversion_target_phrase(reverse: bool, category_ids: list[str] | None = None) -> str:
    """Player-facing description of what conversion will produce."""
    ids = [str(name) for name in (category_ids or []) if name]
    lowered = [name.lower() for name in ids]
    if not lowered or lowered == ["armor"]:
        return "heavy armor" if not reverse else "light armor"
    if len(ids) == 1:
        return category_label(ids[0])
    return "the selected categories"


def convert_button_text(
    *,
    count: int,
    reverse: bool,
    enabled: bool,
    has_blueprint: bool,
    category_ids: list[str] | None = None,
) -> str:
    """Primary CTA copy that states the action in player language."""
    if not has_blueprint:
        return "Select a blueprint to convert"
    if not enabled or count <= 0:
        return "Nothing to convert with current settings"
    block_word = "block" if count == 1 else "blocks"
    ids = [str(name) for name in (category_ids or []) if name]
    lowered = [name.lower() for name in ids]
    armor_only = (not lowered) or lowered == ["armor"]
    if armor_only:
        direction = "heavy armor" if not reverse else "light armor"
        return f"Convert {count} {block_word} to {direction}"
    if len(ids) == 1:
        return f"Convert {count} {block_word} ({category_label(ids[0])})"
    return f"Convert {count} matching {block_word}"


def mode_label(reverse: bool) -> str:
    return "Heavy → Light" if reverse else "Light → Heavy"


def convertible_total(bp_info) -> int:
    """How many blocks the current mapping would rewrite on this blueprint."""
    counts = getattr(bp_info, "convertible_counts", None) or {}
    return int(sum(counts.values()))


def armor_convertible_total(bp_info) -> int:
    """Convertible blocks that are light/heavy armor plates, not thrusters/etc."""
    counts = getattr(bp_info, "convertible_counts", None) or {}
    total = 0
    for pair, count in counts.items():
        source, sep, target = str(pair).partition("->")
        if "Armor" in source or "Armor" in target:
            total += int(count)
    return total


def card_status_label(convertible: int, scanned: bool) -> str:
    if not scanned:
        return "Not scanned yet"
    if convertible <= 0:
        return "Already matches"
    return f"{convertible} ready to convert"


def _checked_category_text(category_ids: list[str] | None) -> str:
    ids = [str(name) for name in (category_ids or []) if name]
    if not ids:
        return "Armor"
    return ", ".join(category_label(name) for name in ids)


def nothing_to_convert_message(category_ids: list[str] | None = None) -> str:
    """Explain a zero-match preview without implying the ship was already converted."""
    checked = _checked_category_text(category_ids)
    return (
        f"No blocks match {checked}, so Convert will not change this ship. "
        "Blocks outside the checked categories stay as they are, including blocks "
        "this app has no verified swap for. "
        "A conversion writes a new copy and does not overwrite the original."
    )


def pending_change_message(count: int, category_ids: list[str] | None = None) -> str:
    """Short outcome line for the control panel after a dry-run."""
    if count <= 0:
        return nothing_to_convert_message(category_ids)
    block_word = "block" if count == 1 else "blocks"
    return (
        f"{count} {block_word} will be rewritten in a new copy. "
        "Blocks outside the checked categories stay as they are. "
        "The original ship is not overwritten."
    )


def armor_change_message(
    *,
    ready: int,
    armor_ready: int,
    reverse: bool,
    category_ids: list[str] | None = None,
) -> str:
    """Before/after summary that keeps non-armor swaps visible."""
    if ready <= 0:
        return nothing_to_convert_message(category_ids)
    block_word = "block" if ready == 1 else "blocks"
    direction = "light" if reverse else "heavy"
    if armor_ready == ready:
        summary = f"{ready} {block_word} will be rewritten in a new copy toward {direction} armor."
    elif armor_ready == 0:
        summary = f"{ready} {block_word} will be rewritten using the selected categories."
    else:
        other = ready - armor_ready
        summary = (
            f"{ready} {block_word} will be rewritten "
            f"({armor_ready} armor toward {direction}, {other} other)."
        )
    return (
        summary
        + " Blocks outside the checked categories stay as they are. "
        "The original ship is not overwritten."
    )


def convert_confirm_body(
    *,
    display_name: str,
    count: int,
    target: str,
    category_text: str,
) -> str:
    block_word = "block" if count == 1 else "blocks"
    return (
        f"Create a new copy of '{display_name}' with {count} {block_word} converted to {target}?\n\n"
        f"Included: {category_text}\n"
        "Blocks outside those categories stay as they are.\n\n"
        "The original blueprint is not changed. Undo removes the new copy."
    )


def copy_created_message(
    name: str,
    scanned: int,
    converted: int,
    *,
    kind: str = "convert",
) -> str:
    """Outcome toast after a GUI copy. The original is never described as overwritten."""
    unchanged = max(0, int(scanned) - int(converted))
    if kind == "se2":
        return (
            f"Wrote a planning file in {name}. "
            f"{converted} of {scanned} blocks used an internal placeholder name; "
            f"{unchanged} kept their Space Engineers 1 subtype. "
            "This folder is not a Space Engineers 2 blueprint, and the original ship was not overwritten."
        )
    if kind == "vanillafy" and converted <= 0:
        return (
            f"Created {name}. No blocks matched the DLC → vanilla list, so the copy matches the original. "
            "Blocks this app has no verified swap for were left as they are. "
            "The original ship was not overwritten."
        )
    if kind == "vanillafy":
        return (
            f"Created {name}. {converted} of {scanned} blocks were replaced with vanilla equivalents. "
            f"{unchanged} block(s) were left as they are. The original ship was not overwritten."
        )
    if converted <= 0:
        return (
            f"Created {name}, but no blocks matched the current settings, so the copy matches the original. "
            "The original ship was not overwritten."
        )
    return (
        f"Created {name}. {converted} of {scanned} blocks changed; "
        f"{unchanged} were left as they are. "
        "The original ship was not overwritten. "
        "Delete any old bp.sbcB5 beside the copy or the game loads the old ship."
    )


def se2_export_confirm_message(display_name: str) -> str:
    return (
        f"Write a planning JSON copy of '{display_name}'?\n\n"
        "The file uses internal placeholder names. It is not a Space Engineers 2 blueprint, "
        "and Space Engineers 2 will not import it.\n\n"
        "To move a grid into Space Engineers 2, use Keen's Grid Exporter in Space Engineers 1 "
        "(chat command /export) and copy that file into the SE2 folder SE1GridsToImport.\n\n"
        "The original blueprint is not changed."
    )


def library_empty_copy(reason: str) -> tuple[str, str]:
    """Title and body for the blueprint list when there is nothing to pick."""
    if reason == "missing":
        return (
            "Space Engineers folder not found",
            "On Windows, ships usually live in %APPDATA%\\SpaceEngineers\\Blueprints\\local.\n"
            "Open that folder, or drop a blueprint folder on this window.\n"
            "Convert always writes a new copy and leaves the original ship alone.",
        )
    if reason == "search":
        return (
            "No ships match that search",
            "Clear the search box to see every ship in this folder.",
        )
    return (
        "No ships in this folder",
        "Each ship is a folder that contains bp.sbc.\n"
        "Open your local blueprints folder, or use File → Import Workshop / Mod.io blueprint.\n"
        "Convert writes a new copy beside the original. It does not overwrite the ship you picked.",
    )
