from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from .categories import (
    DEFAULT_MEMORY_CATEGORIES,
    MemoryCategory,
    category_note,
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
    "category_role",
    "parent_category",
    "prosperity_eligible",
    *INDEX_COLUMNS,
    "category_export_value_share_pct",
    "category_scope_export_value_share_pct",
    "category_hs_patterns",
    "category_note",
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

    monthly: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        price = parse_number(row.get("unit_price_metric"))
        if price is None or price <= 0:
            continue
        monthly[str(row["month"])].append(dict(row))

    index_rows: list[dict[str, object]] = []
    previous_month_rows: list[dict[str, object]] | None = None
    previous_price_index = 100.0
    previous_volume_index = 100.0
    for month, month_rows in sorted(monthly.items()):
        if previous_month_rows is None:
            weighted_index = 100.0
            weighted_volume_index = 100.0
        else:
            price_ratio = _bilateral_price_ratio(month_rows, previous_month_rows)
            weighted_index = (
                previous_price_index * price_ratio
                if price_ratio is not None
                else previous_price_index
            )
            volume_ratio = _bilateral_volume_ratio(month_rows, previous_month_rows)
            weighted_volume_index = (
                previous_volume_index * volume_ratio
                if volume_ratio is not None
                else previous_volume_index
            )
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
                "index_weight_method": "chain_linked_prior_period_export_value",
            }
        )
        previous_month_rows = month_rows
        previous_price_index = weighted_index
        previous_volume_index = weighted_volume_index

    add_bilateral_change_columns(
        index_rows, monthly, "unit_price_metric", "unit_price_basis", "unit_price"
    )
    add_bilateral_change_columns(
        index_rows, monthly, "export_volume", "export_volume_basis", "export_quantity"
    )
    add_bilateral_change_columns(
        index_rows, monthly, "unit_price_metric", "unit_price_basis", "memory_index"
    )
    add_change_columns(index_rows, "export_value_usd", "export_value")
    return index_rows


def _bilateral_price_ratio(
    current_rows: list[dict[str, object]],
    previous_rows: list[dict[str, object]],
) -> float | None:
    """Return a prior-period-value-weighted price ratio for common HS codes.

    Using only the two adjacent periods makes every chain link independent of
    the requested history start.  This avoids changing current growth rates
    merely because a different first month supplied different fixed weights.
    """
    return _bilateral_metric_ratio(
        current_rows,
        previous_rows,
        metric_field="unit_price_metric",
        basis_field="unit_price_basis",
    )


def _bilateral_volume_ratio(
    current_rows: list[dict[str, object]],
    previous_rows: list[dict[str, object]],
) -> float | None:
    return _bilateral_metric_ratio(
        current_rows,
        previous_rows,
        metric_field="export_volume",
        basis_field="export_volume_basis",
    )


def _bilateral_metric_ratio(
    current_rows: list[dict[str, object]],
    previous_rows: list[dict[str, object]],
    metric_field: str,
    basis_field: str,
) -> float | None:
    current_by_hs = {str(row.get("hs_code")): row for row in current_rows}
    previous_by_hs = {str(row.get("hs_code")): row for row in previous_rows}
    relatives: list[tuple[float, float]] = []
    for hs_code in sorted(current_by_hs.keys() & previous_by_hs.keys()):
        current = current_by_hs[hs_code]
        previous = previous_by_hs[hs_code]
        if current.get(basis_field) != previous.get(basis_field):
            continue
        current_value = parse_number(current.get(metric_field))
        previous_value = parse_number(previous.get(metric_field))
        if current_value is None or previous_value is None or previous_value <= 0:
            continue
        weight = parse_number(previous.get("export_value_usd")) or 0.0
        relatives.append((current_value / previous_value, max(weight, 0.0)))
    if not relatives:
        return None
    total_weight = sum(weight for _, weight in relatives)
    if total_weight <= 0:
        return sum(relative for relative, _ in relatives) / len(relatives)
    return sum(relative * weight for relative, weight in relatives) / total_weight


def add_bilateral_change_columns(
    index_rows: list[dict[str, object]],
    monthly: dict[str, list[dict[str, object]]],
    metric_field: str,
    basis_field: str,
    prefix: str,
) -> None:
    comparisons = ((1, "mom_1m"), (3, "mom_3m"), (12, "yoy"))
    for row in index_rows:
        month = str(row["month"])
        for lag, suffix in comparisons:
            previous_rows = monthly.get(shift_month(month, -lag))
            if not previous_rows:
                continue
            ratio = _bilateral_metric_ratio(
                monthly[month], previous_rows, metric_field, basis_field
            )
            if ratio is not None:
                row[f"{prefix}_{suffix}_pct"] = (ratio - 1.0) * 100.0


def build_category_memory_indexes(
    unit_rows: Iterable[dict[str, object]],
    categories: Iterable[MemoryCategory] | None = None,
) -> list[dict[str, object]]:
    rows = list(unit_rows)
    category_rows: list[dict[str, object]] = []
    total_value_by_month: dict[str, float] = defaultdict(float)
    for row in rows:
        month = str(row.get("month", ""))
        if month:
            total_value_by_month[month] += parse_number(row.get("export_value_usd")) or 0.0
    selected_categories = list(categories or DEFAULT_MEMORY_CATEGORIES)
    value_by_category_month: dict[tuple[str, str], float] = defaultdict(float)
    for category in selected_categories:
        for row in rows:
            month = str(row.get("month", ""))
            if month and matches_category(row.get("hs_code"), category):
                value_by_category_month[(category.key, month)] += (
                    parse_number(row.get("export_value_usd")) or 0.0
                )

    for category in selected_categories:
        filtered_rows = [
            row
            for row in rows
            if matches_category(row.get("hs_code"), category)
        ]
        if not filtered_rows:
            continue
        for index_row in build_memory_index(filtered_rows):
            export_value = parse_number(index_row.get("export_value_usd"))
            month = str(index_row.get("month"))
            total_value = total_value_by_month.get(month, 0.0)
            scope_value = (
                value_by_category_month.get((category.parent_key, month), 0.0)
                if category.parent_key
                else total_value
            )
            category_rows.append(
                {
                    "category": category.key,
                    "category_label": category.label,
                    "category_role": category.role,
                    "parent_category": category.parent_key,
                    "prosperity_eligible": category.prosperity_eligible,
                    **index_row,
                    "category_export_value_share_pct": safe_div(
                        (export_value or 0.0) * 100.0,
                        total_value,
                    ),
                    "category_scope_export_value_share_pct": safe_div(
                        (export_value or 0.0) * 100.0,
                        scope_value,
                    ),
                    "category_hs_patterns": category_hs_patterns(category),
                    "category_note": category_note(category),
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
        unique_group = list({_trade_record_signature(record): record for record in group}.values())
        candidates[(month, hs_code)].append(_aggregate_record_group(unique_group))

    selected: list[TradeRecord] = []
    for key in sorted(candidates):
        selected.append(max(candidates[key], key=_record_quality_key))
    return selected


def _trade_record_signature(record: TradeRecord) -> tuple[object, ...]:
    """Identify an identical observation repeated across overlapping inputs."""
    return (
        record.month,
        record.hs_code,
        record.item_name,
        parse_number(record.export_value_usd),
        parse_number(record.export_weight_kg),
        parse_number(record.export_quantity),
        record.quantity_unit,
        parse_number(record.import_value_usd),
        parse_number(record.import_weight_kg),
        _source_group(record.source),
    )


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
