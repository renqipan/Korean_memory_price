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


DEFAULT_MEMORY_CATEGORIES = [
    MemoryCategory(
        key="dram_hbm",
        label="DRAM/HBM",
        hs_patterns=("8542321010", "8542323000"),
    ),
    MemoryCategory(
        key="nand",
        label="NAND/Flash",
        hs_patterns=("8542321030",),
    ),
    MemoryCategory(
        key="ssd",
        label="SSD",
        hs_patterns=("8471704010", "8471709000"),
    ),
    MemoryCategory(
        key="total_memory",
        label="Total memory",
        hs_patterns=(),
        include_all=True,
    ),
]


DEFAULT_FETCH_HS_CODES = ["854232", "8471709000", "8471704010"]


def parse_memory_categories(values: Iterable[str]) -> list[MemoryCategory]:
    categories = list(DEFAULT_MEMORY_CATEGORIES)
    for value in values:
        parsed = parse_memory_category(value)
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
