"""
Mapping category registry and validation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


class MappingValidationError(ValueError):
    """Raised when mapping categories contain invalid definitions."""


@dataclass(frozen=True)
class MappingCategory:
    """
    A named set of source->target subtype mappings.

    Attributes:
        name: Stable category identifier (e.g. armor, thrusters).
        description: User-facing category description.
        pairs: Mapping dictionary from source subtype to target subtype.
        grid_sizes: Supported grid sizes for this category.
        source: Metadata describing where the category came from.
    """

    name: str
    description: str
    pairs: Dict[str, str]
    grid_sizes: Tuple[str, ...] = ("Large", "Small")
    source: str = "built-in"
    enabled_by_default: bool = True
    tags: Tuple[str, ...] = field(default_factory=tuple)

    def reverse_pairs(self) -> Dict[str, str]:
        return {target: source for source, target in self.pairs.items()}


class MappingRegistry:
    """Registry for built-in and profile-provided mapping categories."""

    def __init__(self, categories: Optional[Iterable[MappingCategory]] = None):
        self._categories: Dict[str, MappingCategory] = {}
        self._enabled: Dict[str, bool] = {}
        if categories:
            for category in categories:
                self.register(category)

    def register(self, category: MappingCategory, overwrite: bool = False) -> None:
        self.validate_category(category)
        key = category.name.strip().lower()
        if key in self._categories and not overwrite:
            raise MappingValidationError(f"Category already registered: {category.name}")
        self._categories[key] = category
        self._enabled[key] = category.enabled_by_default

    def unregister(self, name: str) -> None:
        key = name.strip().lower()
        self._categories.pop(key, None)
        self._enabled.pop(key, None)

    def get(self, name: str) -> MappingCategory:
        key = name.strip().lower()
        if key not in self._categories:
            raise KeyError(f"Unknown mapping category: {name}")
        return self._categories[key]

    def exists(self, name: str) -> bool:
        return name.strip().lower() in self._categories

    def list_categories(self) -> List[MappingCategory]:
        return [self._categories[name] for name in sorted(self._categories)]

    def set_enabled(self, name: str, enabled: bool) -> None:
        key = name.strip().lower()
        if key not in self._categories:
            raise KeyError(f"Unknown mapping category: {name}")
        self._enabled[key] = bool(enabled)

    def is_enabled(self, name: str) -> bool:
        key = name.strip().lower()
        return self._enabled.get(key, False)

    def enabled_names(self) -> List[str]:
        return [name for name in sorted(self._categories) if self._enabled.get(name, False)]

    def build_mapping(
        self,
        reverse: bool = False,
        enabled_categories: Optional[Sequence[str]] = None,
    ) -> Dict[str, str]:
        """
        Build a merged mapping dictionary from selected categories.

        Args:
            reverse: If True, swaps source and target for each pair.
            enabled_categories: Optional explicit category names. If omitted,
                registry enabled flags are used.
        """
        selected: List[MappingCategory] = []
        if enabled_categories is None:
            for key in self.enabled_names():
                selected.append(self._categories[key])
        else:
            for name in enabled_categories:
                selected.append(self.get(name))

        if reverse:
            # Many-to-one categories (DLC → vanilla) have no unique inverse.
            # Reversing them collapses targets and collides with real swaps
            # such as LargeAssembler ↔ BasicAssembler.
            reversible: List[MappingCategory] = []
            one_way: List[str] = []
            for category in selected:
                if self.category_is_reversible(category):
                    reversible.append(category)
                else:
                    one_way.append(category.name)
            if selected and not reversible:
                raise MappingValidationError(
                    "Cannot reverse one-way categories (multiple sources share a target): "
                    + ", ".join(one_way)
                )
            selected = reversible

        merged: Dict[str, str] = {}
        target_to_source: Dict[str, str] = {}

        for category in selected:
            pairs = category.reverse_pairs() if reverse else category.pairs
            for source, target in pairs.items():
                if source in merged and merged[source] != target:
                    raise MappingValidationError(
                        f"Duplicate source '{source}' across categories "
                        f"({merged[source]} vs {target})"
                    )
                if reverse and target in target_to_source and target_to_source[target] != source:
                    raise MappingValidationError(
                        f"Duplicate target '{target}' across categories "
                        f"({target_to_source[target]} and {source})"
                    )
                merged[source] = target
                target_to_source[target] = source

        self.validate_pairs(merged, allow_duplicate_targets=not reverse)
        return merged

    @staticmethod
    def category_is_reversible(category: MappingCategory) -> bool:
        """True when every target is unique, so the swap has one inverse."""
        targets = list(category.pairs.values())
        return len(targets) == len(set(targets))

    @staticmethod
    def validate_pairs(pairs: Dict[str, str], allow_duplicate_targets: bool = True) -> None:
        if not pairs:
            return

        targets = set()
        for source, target in pairs.items():
            if not source or not target:
                raise MappingValidationError("Mappings cannot contain empty source/target values")
            if source == target:
                raise MappingValidationError(f"Identity mapping is not allowed: {source} -> {target}")
            if not allow_duplicate_targets and target in targets:
                raise MappingValidationError(f"Duplicate target detected in merged mapping: {target}")
            targets.add(target)

        for source, target in pairs.items():
            if target in pairs and pairs[target] == source:
                raise MappingValidationError(f"Circular swap detected: {source} <-> {target}")

    @classmethod
    def validate_category(cls, category: MappingCategory) -> None:
        if not category.name or not category.name.strip():
            raise MappingValidationError("Category name cannot be empty")
        if not category.description or not category.description.strip():
            raise MappingValidationError(f"Category '{category.name}' is missing a description")
        if not isinstance(category.pairs, dict) or not category.pairs:
            raise MappingValidationError(f"Category '{category.name}' has no mapping pairs")
        cls.validate_pairs(category.pairs)


def authored_exchange_targets(
    registry: MappingRegistry,
    extra_one_way: Optional[Dict[str, str]] = None,
) -> Dict[str, List[str]]:
    """
    Subtype targets taken only from registered pairs.

    Injective categories contribute both directions. One-way categories
    contribute forward pairs only. Callers must not synthesize subtype IDs.
    """
    index: Dict[str, List[str]] = {}

    def add(source: str, target: str) -> None:
        if not source or not target or source == target:
            return
        bucket = index.setdefault(source, [])
        if target not in bucket:
            bucket.append(target)

    for category in registry.list_categories():
        injective = MappingRegistry.category_is_reversible(category)
        for source, target in category.pairs.items():
            add(source, target)
            if injective:
                add(target, source)

    if extra_one_way:
        for source, target in extra_one_way.items():
            add(source, target)
    return index


def coerce_mergeable_categories(
    registry: MappingRegistry,
    names: Sequence[str],
) -> Tuple[List[str], bool]:
    """
    Keep ``names`` when they merge in the forward direction.

    Returns ``(["armor"], True)`` when the saved set collides, so a GUI
    launch does not die on a stale settings file.
    """
    requested = [name for name in names if name]
    if not requested:
        return ["armor"], False
    try:
        registry.build_mapping(reverse=False, enabled_categories=requested)
    except MappingValidationError:
        return ["armor"], True
    return list(requested), False


def build_registry(include_builtin: bool = True) -> MappingRegistry:
    """
    Build a registry with built-in categories.
    """
    registry = MappingRegistry()
    if include_builtin:
        from mappings.armor import get_category as get_armor
        from mappings.functional import get_category as get_functional
        from mappings.thrusters import get_category as get_thrusters
        from mappings.weapons import get_category as get_weapons
        from mappings.dlc_substitution import get_category as get_dlc_sub
        from mappings.prototech import (
            CATEGORY_DESCRIPTION as PROTOTECH_DESCRIPTION,
            CATEGORY_NAME as PROTOTECH_NAME,
            CATEGORY_TAGS as PROTOTECH_TAGS,
            VANILLA_TO_PROTOTECH_PAIRS,
        )

        for category in (
            get_armor(),
            get_thrusters(),
            get_weapons(),
            get_functional(),
            get_dlc_sub(),
        ):
            registry.register(category)

        # Built here so mappings.prototech never imports this module.
        registry.register(
            MappingCategory(
                name=PROTOTECH_NAME,
                description=PROTOTECH_DESCRIPTION,
                pairs=VANILLA_TO_PROTOTECH_PAIRS,
                grid_sizes=("Large", "Small"),
                source="endgame",
                enabled_by_default=False,
                tags=PROTOTECH_TAGS,
            )
        )
    return registry

