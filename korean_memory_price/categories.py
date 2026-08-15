from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

from .utils import normalize_hs_code


@dataclass(frozen=True, slots=True)
class MemoryCategory:
    key: str
    label: str
    hs_patterns: tuple[str, ...]
    include_all: bool = False
    note: str = ""
    role: str = "context"
    parent_key: str = ""
    prosperity_eligible: bool = False


CORE_CATEGORY_KEY = "semiconductor_memory"


DEFAULT_MEMORY_CATEGORIES = [
    MemoryCategory(
        key=CORE_CATEGORY_KEY,
        label="Semiconductor memory IC",
        hs_patterns=("854232",),
        note="Core memory-IC scope used for the price and prosperity indexes.",
        role="core",
    ),
    MemoryCategory(
        key="dram",
        label="DRAM IC",
        hs_patterns=("8542321010",),
        note=(
            "DRAM integrated circuits only. Korea's official ICT DRAM total also "
            "includes HSK 8473304060 DRAM modules."
        ),
        role="component",
        parent_key=CORE_CATEGORY_KEY,
        prosperity_eligible=True,
    ),
    MemoryCategory(
        key="sram",
        label="SRAM",
        hs_patterns=("8542321020",),
        note="KCS HSK code explicitly classified as SRAM.",
        role="component",
        parent_key=CORE_CATEGORY_KEY,
        prosperity_eligible=True,
    ),
    MemoryCategory(
        key="flash_memory",
        label="Flash memory (NAND proxy)",
        hs_patterns=("8542321030",),
        note="KCS Flash-memory line; use as a NAND proxy rather than a pure NAND series.",
        role="component",
        parent_key=CORE_CATEGORY_KEY,
        prosperity_eligible=True,
    ),
    MemoryCategory(
        key="multichip_memory",
        label="Multichip memory IC (HBM proxy)",
        hs_patterns=("8542323000",),
        note="Multichip IC line used as an HBM-related proxy; it is not a pure HBM classification.",
        role="component",
        parent_key=CORE_CATEGORY_KEY,
        prosperity_eligible=True,
    ),
    MemoryCategory(
        key="mco_memory",
        label="MCO memory IC",
        hs_patterns=("8542324000",),
        note="Multi-component integrated-circuit memory line.",
        role="component",
        parent_key=CORE_CATEGORY_KEY,
        prosperity_eligible=True,
    ),
    MemoryCategory(
        key="other_memory_ic",
        label="Other memory IC",
        hs_patterns=("8542321090", "8542322000"),
        note="Other and hybrid memory-integrated-circuit lines within HSK 854232.",
        role="component",
        parent_key=CORE_CATEGORY_KEY,
        prosperity_eligible=True,
    ),
    MemoryCategory(
        key="dram_module",
        label="DRAM module",
        hs_patterns=("8473304060",),
        note=(
            "DRAM modules reported outside HS 854232; kept outside the core "
            "memory-IC prosperity index."
        ),
        role="official_component",
        parent_key="ict_memory_semiconductors",
    ),
    MemoryCategory(
        key="ict_dram",
        label="Official ICT DRAM scope",
        hs_patterns=("8542321010", "8473304060"),
        note=(
            "Korean official ICT-export DRAM scope: DRAM IC plus DRAM module, "
            "as confirmed by the KOSIS statistical agency response."
        ),
        role="official_scope",
        parent_key="ict_memory_semiconductors",
    ),
    MemoryCategory(
        key="ict_memory_semiconductors",
        label="Official ICT memory-semiconductor scope",
        hs_patterns=("854232", "8473304060"),
        note=(
            "Official ICT memory-semiconductor reconciliation scope. It is "
            "reported separately because the module line is not a memory IC."
        ),
        role="official_scope",
    ),
    MemoryCategory(
        key="solid_state_media",
        label="Solid-state non-volatile media",
        hs_patterns=("852351",),
        note="Separate solid-state-media scope; includes more than SSDs and is not used in the core memory-IC prosperity score.",
        role="context",
    ),
    MemoryCategory(
        key="storage_devices",
        label="Storage devices",
        hs_patterns=("847170",),
        note=(
            "General computer storage devices; includes HDD and other units and "
            "must not be labelled as SSD. Its aggregate unit value is highly "
            "mix-sensitive, so it is excluded from the overview chart and score."
        ),
        role="context",
    ),
    MemoryCategory(
        key="all_tracked_storage",
        label="All tracked memory and storage",
        hs_patterns=(),
        include_all=True,
        note="Aggregate of every fetched memory-IC, solid-state-media and storage-device record.",
        role="aggregate",
    ),
]


DEFAULT_FETCH_HS_CODES = ["854232", "8473304060", "852351", "847170"]


def parse_memory_categories(values: Iterable[str]) -> list[MemoryCategory]:
    categories = list(DEFAULT_MEMORY_CATEGORIES)
    for value in values:
        parsed = parse_memory_category(value)
        existing = next(
            (category for category in categories if category.key == parsed.key),
            None,
        )
        if existing is not None:
            parsed = MemoryCategory(
                key=parsed.key,
                label=parsed.label,
                hs_patterns=parsed.hs_patterns,
                note=existing.note,
                role=existing.role,
                parent_key=existing.parent_key,
                prosperity_eligible=existing.prosperity_eligible,
            )
        categories = [
            parsed if category.key == parsed.key else category
            for category in categories
        ]
        if not any(category.key == parsed.key for category in categories):
            categories.append(parsed)
    return categories


def parse_memory_category(value: str) -> MemoryCategory:
    if "=" not in value:
        raise ValueError(
            "category must be formatted as name=hs1,hs2 or name:Label=hs1,hs2"
        )
    name_part, hs_part = value.split("=", 1)
    if ":" in name_part:
        key_part, label = name_part.split(":", 1)
    else:
        key_part = name_part
        label = name_part.replace("_", " ").strip().title()
    key = _normalize_category_key(key_part)
    patterns = tuple(
        normalize_hs_code(item)
        for item in re.split(r"[,;]", hs_part)
        if normalize_hs_code(item)
    )
    if not key or not patterns:
        raise ValueError(
            "category must include a non-empty name and at least one HS code"
        )
    return MemoryCategory(key=key, label=label.strip() or key, hs_patterns=patterns)


def matches_category(hs_code: object, category: MemoryCategory) -> bool:
    if category.include_all:
        return True
    normalized = normalize_hs_code(hs_code)
    return any(_matches_hs_pattern(normalized, pattern) for pattern in category.hs_patterns)


def category_hs_patterns(category: MemoryCategory) -> str:
    if category.include_all:
        return "*"
    return ";".join(category.hs_patterns)


def category_note(category: MemoryCategory) -> str:
    return category.note


def _matches_hs_pattern(hs_code: str, pattern: str) -> bool:
    if not hs_code or not pattern:
        return False
    if hs_code == pattern:
        return True
    return len(pattern) < len(hs_code) and hs_code.startswith(pattern)


def _normalize_category_key(value: str) -> str:
    lowered = value.strip().lower()
    lowered = re.sub(r"[^a-z0-9]+", "_", lowered)
    return lowered.strip("_")
