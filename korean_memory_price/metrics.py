from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from .categories import (
    DEFAULT_MEMORY_CATEGORIES,
    MemoryCategory,
    category_hs_patterns,
    matches_category,
)
from .models import TradeRecord
from .utils import parse_number, pct_change, safe_div, shift_month, sort_by_month


UNIT_PRICE_COLUMNS = [
    "month",
    "hs_code",
    "item_name",
    "source",
    "source_group",
    "record_count",
    "export_value_usd",
    "export_weight_kg",
    "export_quantity",
    "quantity_unit",
    "unit_usd_per_kg",
    "unit_usd_per_quantity",
    "unit_price_metric",
    "unit_price_basis",
    "export_volume",
    "export_volume_basis",
]


INDEX_COLUMNS = [
    "month",
    "unit_price_index",
    "unit_price_mom_1m_pct",
    "unit_price_mom_3m_pct",
    "unit_price_yoy_pct",
    "export_quantity_index",
    "export_quantity_mom_1m_pct",
    "export_quantity_yoy_pct",
    "memory_index",
    "memory_index_mom_1m_pct",
    "memory_index_mom_3m_pct",
    "memory_index_yoy_pct",
    "export_value_usd",
    "export_value_mom_1m_pct",
    "export_value_yoy_pct",
    "export_weight_kg",
    "export_volume",
    "export_volume_basis",
    "hs_codes",
    "hs_count",
    "index_weight_method",
]


CATEGORY_INDEX_COLUMNS = [
    "category",
    "category_label",
    *INDEX_COLUMNS,
    "category_hs_patterns",
]


def build_unit_price_rows(records: Iterable[TradeRecord]) -> list[dict[str, object]]:
    base_rows: list[dict[str, object]] = []
    for record in _dedupe_trade_records(records):
        unit_usd_per_kg = safe_div(record.export_value_usd, record.export_weight_kg)
        unit_usd_per_quantity = safe_div(record.export_value_usd, record.export_quantity)
        base_rows.append(
            {
                "month": record.month,
                "hs_code": record.hs_code,
                "item_name": record.item_name,
                "source": record.source,
                "source_group": _source_group(record.source),
                "record_count": record.raw.get("record_count", 1),
                "export_value_usd": record.export_value_usd,
                "export_weight_kg": record.export_weight_kg,
                "export_quantity": record.export_quantity,
                "quantity_unit": record.quantity_unit,
                "unit_usd_per_kg": unit_usd_per_kg,
                "unit_usd_per_quantity": unit_usd_per_quantity,
            }
        )

    basis_by_hs = _choose_stable_basis_by_hs(base_rows)
    rows: list[dict[str, object]] = []
    for row in base_rows:
        basis = basis_by_hs.get(str(row["hs_code"]), "kg")
        if basis == "quantity":
            unit_price_metric = row.get("unit_usd_per_quantity")
            export_volume = row.get("export_quantity")
            volume_basis = row.get("quantity_unit") or "quantity"
        else:
            unit_price_metric = row.get("unit_usd_per_kg")
            export_volume = row.get("export_weight_kg")
            volume_basis = "kg"
        row["unit_price_metric"] = unit_price_metric
        row["unit_price_basis"] = volume_basis
        row["export_volume"] = export_volume
        row["export_volume_basis"] = volume_basis
        rows.append(row)
    return sorted(rows, key=lambda row: (str(row["month"]), str(row["hs_code"]), str(row["source"])))


def build_memory_index(unit_rows: Iterable[dict[str, object]]) -> list[dict[str, object]]:
    rows = [
        dict(row)
        for row in unit_rows
        if parse_number(row.get("unit_price_metric")) is not None
        and parse_number(row.get("unit_price_metric")) != 0
    ]
    rows.sort(key=lambda row: (str(row["hs_code"]), str(row["month"])))

    base_price_by_hs: dict[str, float] = {}
    base_volume_by_hs: dict[str, float] = {}
    base_weight_by_hs: dict[str, float] = {}
    for row in rows:
        hs_code = str(row["hs_code"])
        price = parse_number(row.get("unit_price_metric"))
        volume = parse_number(row.get("export_volume"))
        export_value = parse_number(row.get("export_value_usd"))
        if price is not None and price > 0 and hs_code not in base_price_by_hs:
            base_price_by_hs[hs_code] = price
        if volume is not None and volume > 0 and hs_code not in base_volume_by_hs:
            base_volume_by_hs[hs_code] = volume
        if export_value is not None and export_value > 0 and hs_code not in base_weight_by_hs:
            base_weight_by_hs[hs_code] = export_value

    monthly: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        hs_code = str(row["hs_code"])
        price = parse_number(row.get("unit_price_metric"))
        volume = parse_number(row.get("export_volume"))
        base_price = base_price_by_hs.get(hs_code)
        base_volume = base_volume_by_hs.get(hs_code)
        if price is None or not base_price:
            continue
        indexed = dict(row)
        indexed["hs_price_index"] = price / base_price * 100.0
        if volume is not None and base_volume:
            indexed["hs_volume_index"] = volume / base_volume * 100.0
        monthly[str(row["month"])].append(indexed)

    index_rows: list[dict[str, object]] = []
    for month, month_rows in sorted(monthly.items()):
        weights = [
            base_weight_by_hs.get(str(row["hs_code"]), 0.0)
            for row in month_rows
        ]
        if sum(weights) <= 0:
            weights = [1.0 for _ in month_rows]
        weighted_index = sum(
            (parse_number(row.get("hs_price_index")) or 0.0) * weight
            for row, weight in zip(month_rows, weights)
        ) / sum(weights)
        volume_index_values = [
            (parse_number(row.get("hs_volume_index")), weight)
            for row, weight in zip(month_rows, weights)
            if parse_number(row.get("hs_volume_index")) is not None
        ]
        weighted_volume_index = None
        if volume_index_values:
            total_volume_weight = sum(weight for _, weight in volume_index_values)
            if total_volume_weight > 0:
                weighted_volume_index = sum(
                    (value or 0.0) * weight for value, weight in volume_index_values
                ) / total_volume_weight
        volume_basis = _common_basis(month_rows)
        index_rows.append(
            {
                "month": month,
                "unit_price_index": weighted_index,
                "memory_index": weighted_index,
                "export_quantity_index": weighted_volume_index,
                "export_value_usd": sum(parse_number(row.get("export_value_usd")) or 0.0 for row in month_rows),
                "export_weight_kg": sum(parse_number(row.get("export_weight_kg")) or 0.0 for row in month_rows),
                "export_volume": sum(parse_number(row.get("export_volume")) or 0.0 for row in month_rows),
                "export_volume_basis": volume_basis,
                "hs_codes": ";".join(sorted({str(row["hs_code"]) for row in month_rows})),
                "hs_count": len({str(row["hs_code"]) for row in month_rows}),
                "index_weight_method": "fixed_first_valid_export_value",
            }
        )

    add_change_columns(index_rows, "unit_price_index", "unit_price")
    add_change_columns(index_rows, "export_quantity_index", "export_quantity")
    add_change_columns(index_rows, "memory_index", "memory_index")
    add_change_columns(index_rows, "export_value_usd", "export_value")
    return index_rows


def build_category_memory_indexes(
    unit_rows: Iterable[dict[str, object]],
    categories: Iterable[MemoryCategory] | None = None,
) -> list[dict[str, object]]:
    rows = list(unit_rows)
    category_rows: list[dict[str, object]] = []
    for category in categories or DEFAULT_MEMORY_CATEGORIES:
        filtered_rows = [
            row
            for row in rows
            if matches_category(row.get("hs_code"), category)
        ]
        if not filtered_rows:
            continue
        for index_row in build_memory_index(filtered_rows):
            category_rows.append(
                {
                    "category": category.key,
                    "category_label": category.label,
                    **index_row,
                    "category_hs_patterns": category_hs_patterns(category),
                }
            )
    return sorted(
        category_rows,
        key=lambda row: (str(row.get("category", "")), str(row.get("month", ""))),
    )


def _dedupe_trade_records(records: Iterable[TradeRecord]) -> list[TradeRecord]:
    grouped: dict[tuple[str, str, str], list[TradeRecord]] = defaultdict(list)
    for record in records:
        if not record.month or not record.hs_code:
            continue
        grouped[(record.month, record.hs_code, _source_group(record.source))].append(record)

    candidates: dict[tuple[str, str], list[TradeRecord]] = defaultdict(list)
    for (month, hs_code, _), group in grouped.items():
        candidates[(month, hs_code)].append(_aggregate_record_group(group))

    selected: list[TradeRecord] = []
    for key in sorted(candidates):
        selected.append(max(candidates[key], key=_record_quality_key))
    return selected


def _aggregate_record_group(records: list[TradeRecord]) -> TradeRecord:
    first = records[0]
    quantity_unit = _common_quantity_unit(records)
    quantity = None
    if quantity_unit != "mixed":
        quantity = _sum_numbers(record.export_quantity for record in records)
    return TradeRecord(
        month=first.month,
        hs_code=first.hs_code,
        item_name=_first_nonempty(record.item_name for record in records),
        export_value_usd=_sum_numbers(record.export_value_usd for record in records),
        export_weight_kg=_sum_numbers(record.export_weight_kg for record in records),
        export_quantity=quantity,
        quantity_unit=quantity_unit,
        import_value_usd=_sum_numbers(record.import_value_usd for record in records),
        import_weight_kg=_sum_numbers(record.import_weight_kg for record in records),
        source=";".join(sorted({record.source for record in records if record.source})),
        raw={"record_count": len(records)},
    )


def _record_quality_key(record: TradeRecord) -> tuple[int, int, int, int, float]:
    has_value = 1 if parse_number(record.export_value_usd) is not None else 0
    has_quantity = 1 if parse_number(record.export_quantity) is not None else 0
    has_weight = 1 if parse_number(record.export_weight_kg) is not None else 0
    source_score = {"trass": 3, "kcs": 2, "manual": 1}.get(_source_group(record.source), 0)
    export_value = parse_number(record.export_value_usd) or 0.0
    return (has_value, has_quantity, has_weight, source_score, export_value)


def _choose_stable_basis_by_hs(rows: list[dict[str, object]]) -> dict[str, str]:
    counts: dict[str, dict[str, int]] = defaultdict(lambda: {"quantity": 0, "kg": 0})
    for row in rows:
        hs_code = str(row["hs_code"])
        if parse_number(row.get("unit_usd_per_quantity")) is not None:
            counts[hs_code]["quantity"] += 1
        if parse_number(row.get("unit_usd_per_kg")) is not None:
            counts[hs_code]["kg"] += 1
    return {
        hs_code: "quantity" if values["quantity"] >= values["kg"] and values["quantity"] > 0 else "kg"
        for hs_code, values in counts.items()
    }


def _source_group(source: str) -> str:
    lowered = (source or "").lower()
    if "trass" in lowered:
        return "trass"
    if "kcs" in lowered:
        return "kcs"
    if "manual" in lowered:
        return "manual"
    return lowered.split(":", 1)[0] or "manual"


def _common_quantity_unit(records: list[TradeRecord]) -> str:
    units = {record.quantity_unit for record in records if record.quantity_unit}
    if len(units) > 1:
        return "mixed"
    if len(units) == 1:
        return next(iter(units))
    return ""


def _sum_numbers(values: Iterable[object]) -> float | None:
    numbers = [number for number in (parse_number(value) for value in values) if number is not None]
    return sum(numbers) if numbers else None


def _first_nonempty(values: Iterable[str]) -> str:
    return next((value for value in values if value), "")


def add_change_columns(rows: list[dict[str, object]], field: str, prefix: str) -> None:
    rows.sort(key=lambda row: str(row["month"]))
    rows_by_month = {str(row["month"]): row for row in rows}
    for row in rows:
        month = str(row["month"])
        prior_1m = rows_by_month.get(shift_month(month, -1))
        prior_3m = rows_by_month.get(shift_month(month, -3))
        prior_12m = rows_by_month.get(shift_month(month, -12))
        if prior_1m:
            row[f"{prefix}_mom_1m_pct"] = pct_change(row.get(field), prior_1m.get(field))
        if prior_3m:
            row[f"{prefix}_mom_3m_pct"] = pct_change(row.get(field), prior_3m.get(field))
        if prior_12m:
            row[f"{prefix}_yoy_pct"] = pct_change(row.get(field), prior_12m.get(field))


def latest_summary(index_rows: list[dict[str, object]]) -> dict[str, object]:
    if not index_rows:
        return {}
    row = sort_by_month(index_rows)[-1]
    return {
        "month": row.get("month"),
        "memory_index": row.get("memory_index"),
        "memory_index_mom_1m_pct": row.get("memory_index_mom_1m_pct"),
        "memory_index_mom_3m_pct": row.get("memory_index_mom_3m_pct"),
        "memory_index_yoy_pct": row.get("memory_index_yoy_pct"),
        "export_value_yoy_pct": row.get("export_value_yoy_pct"),
        "export_quantity_yoy_pct": row.get("export_quantity_yoy_pct"),
        "unit_price_mom_1m_pct": row.get("unit_price_mom_1m_pct"),
        "unit_price_yoy_pct": row.get("unit_price_yoy_pct"),
    }


def _common_basis(rows: list[dict[str, object]]) -> str:
    bases = {str(row.get("export_volume_basis") or "") for row in rows}
    bases.discard("")
    if len(bases) == 1:
        return next(iter(bases))
    if not bases:
        return ""
    return "mixed_index"
