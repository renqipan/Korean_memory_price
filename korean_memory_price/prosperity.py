from __future__ import annotations

from .utils import parse_number, shift_month


PROSPERITY_COLUMNS = [
    "month",
    "export_value_yoy_pct",
    "export_quantity_yoy_pct",
    "unit_price_yoy_pct",
    "unit_price_mom_1m_pct",
    "memory_score",
    "memory_score_3m_avg",
    "score_mom_1m",
    "score_mom_3m",
    "memory_regime",
    "cycle_phase",
    "unit_value_volume_confirmation",
    "price_volume_confirmation",
    "revenue_confirmation",
    "score_confidence",
    "indicator_completeness",
    "comparison_coverage_mom_1m_pct",
    "comparison_coverage_yoy_pct",
    "valid_indicator_count",
    "value_score",
    "volume_score",
    "unit_value_score",
    "price_score",
    "momentum_score",
    "export_value_component",
    "export_quantity_component",
    "unit_price_yoy_component",
    "unit_price_mom_component",
    "unit_price_index",
    "export_quantity_index",
    "export_volume_basis",
    "export_value_usd",
    "score_method",
    "signal_basis",
    "model_version",
]


OVERALL_PROSPERITY_COLUMNS = [
    "month",
    "overall_memory_prosperity_score",
    "overall_memory_prosperity_3m_avg",
    "overall_score_mom_1m",
    "overall_score_mom_3m",
    "overall_memory_regime",
    "core_memory_score",
    "category_breadth_score",
    "category_unit_value_cycle_score",
    "category_signal_coverage_pct",
    "category_positive_share_pct",
    "category_positive_count",
    "category_valid_count",
    "dominant_category",
    "dominant_category_share_pct",
    "model_version",
]


MODEL_VERSION = "memory-prosperity-v5.2"

OVERALL_MODEL_VERSION = "overall-memory-prosperity-v3.2"

OVERALL_SCORE_WEIGHT = 0.80
CATEGORY_CYCLE_WEIGHT = 0.20


MODEL_WEIGHTS = {
    # Export value is approximately price x volume, so it remains a diagnostic
    # confirmation signal and deliberately receives no independent score weight.
    "export_value_yoy_pct": 0.0,
    "export_quantity_yoy_pct": 0.35,
    "unit_price_yoy_pct": 0.4875,
    "unit_price_mom_1m_pct": 0.1625,
}


MODEL_THRESHOLDS = {
    "export_value_yoy_pct": 50.0,
    "export_quantity_yoy_pct": 30.0,
    "unit_price_yoy_pct": 40.0,
    "unit_price_mom_1m_pct": 8.0,
}


SCORED_INDICATORS = tuple(
    key for key, weight in MODEL_WEIGHTS.items() if weight > 0
)


def build_prosperity_scores(
    index_rows: list[dict[str, object]],
    min_indicators: int = 3,
) -> list[dict[str, object]]:
    score_rows: list[dict[str, object]] = []
    for row in sorted(index_rows, key=lambda item: str(item.get("month", ""))):
        components = {
            key: _normalize_component(row.get(key), MODEL_THRESHOLDS[key])
            for key in MODEL_WEIGHTS
        }
        available = {
            key: value
            for key, value in components.items()
            if key in SCORED_INDICATORS and value is not None
        }
        score = None
        regime = "insufficient_data"
        if len(available) >= min_indicators:
            total_weight = sum(MODEL_WEIGHTS[key] for key in available)
            weighted_signal = sum(
                available[key] * MODEL_WEIGHTS[key] for key in available
            ) / total_weight
            score = max(0.0, min(100.0, 50.0 + 50.0 * weighted_signal))
            regime = classify_memory_regime(score)

        score_rows.append(
            {
                "month": row.get("month"),
                "export_value_yoy_pct": row.get("export_value_yoy_pct"),
                "export_quantity_yoy_pct": row.get("export_quantity_yoy_pct"),
                "unit_price_yoy_pct": row.get("unit_price_yoy_pct"),
                "unit_price_mom_1m_pct": row.get("unit_price_mom_1m_pct"),
                "memory_score": score,
                "memory_score_3m_avg": None,
                "score_mom_1m": None,
                "score_mom_3m": None,
                "memory_regime": regime,
                "cycle_phase": "insufficient_data",
                "unit_value_volume_confirmation": classify_price_volume_confirmation(row),
                # Backward-compatible field name; the value now says unit_value.
                "price_volume_confirmation": classify_price_volume_confirmation(row),
                "revenue_confirmation": classify_revenue_confirmation(row),
                "score_confidence": len(available) / len(SCORED_INDICATORS),
                "indicator_completeness": len(available) / len(SCORED_INDICATORS),
                "comparison_coverage_mom_1m_pct": row.get("comparison_coverage_mom_1m_pct"),
                "comparison_coverage_yoy_pct": row.get("comparison_coverage_yoy_pct"),
                "valid_indicator_count": len(available),
                "value_score": _component_score(components["export_value_yoy_pct"]),
                "volume_score": _component_score(components["export_quantity_yoy_pct"]),
                "unit_value_score": _component_score(components["unit_price_yoy_pct"]),
                # Backward-compatible alias.
                "price_score": _component_score(components["unit_price_yoy_pct"]),
                "momentum_score": _component_score(components["unit_price_mom_1m_pct"]),
                "export_value_component": components["export_value_yoy_pct"],
                "export_quantity_component": components["export_quantity_yoy_pct"],
                "unit_price_yoy_component": components["unit_price_yoy_pct"],
                "unit_price_mom_component": components["unit_price_mom_1m_pct"],
                "unit_price_index": _first_value(row, "unit_price_index", "memory_index"),
                "export_quantity_index": row.get("export_quantity_index"),
                "export_volume_basis": row.get("export_volume_basis"),
                "export_value_usd": row.get("export_value_usd"),
                "score_method": "65% export-unit-value cycle + 35% export-volume cycle; export value diagnostic only",
                "signal_basis": "korean_export_unit_value_and_weight_or_quantity_proxy",
                "model_version": MODEL_VERSION,
            }
        )
    _add_score_trends(score_rows)
    for row in score_rows:
        row["cycle_phase"] = classify_cycle_phase(row)
    return score_rows


def classify_memory_regime(score: float | None) -> str:
    if score is None:
        return "insufficient_data"
    if score >= 75:
        return "boom"
    if score >= 60:
        return "expansion"
    if score >= 45:
        return "neutral"
    if score >= 30:
        return "contraction"
    return "downturn"


def classify_cycle_phase(row: dict[str, object]) -> str:
    score = parse_number(row.get("memory_score"))
    score_change = parse_number(row.get("score_mom_1m"))
    price_yoy = parse_number(row.get("unit_price_yoy_pct"))
    price_mom = parse_number(row.get("unit_price_mom_1m_pct"))
    volume_yoy = parse_number(row.get("export_quantity_yoy_pct"))
    value_yoy = parse_number(row.get("export_value_yoy_pct"))

    if score is None:
        return "insufficient_data"
    if score >= 75 and (volume_yoy or 0) > 0 and (price_yoy or 0) > 0:
        return "broad_based_boom"
    if score >= 75 and (price_yoy or 0) > 0:
        return "unit_value_led_boom"
    if score >= 60 and (price_mom or 0) > 0 and (score_change or 0) > 0:
        return "recovery"
    if score >= 60:
        return "expansion"
    if score >= 45 and (price_mom or 0) < 0:
        return "cooling"
    if score < 45 and (value_yoy or 0) < 0:
        return "contraction"
    if score < 45:
        return "weak"
    return "neutral"


def classify_price_volume_confirmation(row: dict[str, object]) -> str:
    price_yoy = parse_number(row.get("unit_price_yoy_pct"))
    volume_yoy = parse_number(row.get("export_quantity_yoy_pct"))
    if price_yoy is None or volume_yoy is None:
        return "insufficient_data"
    if price_yoy > 0 and volume_yoy > 0:
        return "unit_value_and_volume_up"
    if price_yoy > 0 and volume_yoy <= 0:
        return "unit_value_up_volume_weak"
    if price_yoy <= 0 and volume_yoy > 0:
        return "unit_value_weak_volume_up"
    return "unit_value_and_volume_weak"


def classify_revenue_confirmation(row: dict[str, object]) -> str:
    value_yoy = parse_number(row.get("export_value_yoy_pct"))
    price_yoy = parse_number(row.get("unit_price_yoy_pct"))
    volume_yoy = parse_number(row.get("export_quantity_yoy_pct"))
    if value_yoy is None or price_yoy is None or volume_yoy is None:
        return "insufficient_data"
    implied_direction = (1.0 + price_yoy / 100.0) * (1.0 + volume_yoy / 100.0) - 1.0
    if value_yoy == 0 and implied_direction == 0:
        return "confirmed"
    if value_yoy * implied_direction > 0:
        return "confirmed"
    return "divergent"


def build_overall_prosperity_index(
    prosperity_rows: list[dict[str, object]],
    category_rows: list[dict[str, object]],
) -> list[dict[str, object]]:
    categories_by_month: dict[str, list[dict[str, object]]] = {}
    for row in category_rows:
        if not _is_prosperity_eligible(row):
            continue
        month = str(row.get("month", ""))
        if month:
            categories_by_month.setdefault(month, []).append(row)

    overall_rows: list[dict[str, object]] = []
    for row in sorted(prosperity_rows, key=lambda item: str(item.get("month", ""))):
        month = str(row.get("month", ""))
        core_score = parse_number(row.get("memory_score"))
        category_summary = _category_cycle_summary(categories_by_month.get(month, []))
        category_score = category_summary["category_unit_value_cycle_score"]
        overall_score = _combine_overall_score(core_score, category_score)
        overall_rows.append(
            {
                "month": row.get("month"),
                "overall_memory_prosperity_score": overall_score,
                "overall_memory_prosperity_3m_avg": None,
                "overall_score_mom_1m": None,
                "overall_score_mom_3m": None,
                "overall_memory_regime": classify_memory_regime(overall_score),
                "core_memory_score": core_score,
                **category_summary,
                "model_version": OVERALL_MODEL_VERSION,
            }
        )
    _add_overall_score_trends(overall_rows)
    for row in overall_rows:
        row["overall_memory_regime"] = classify_memory_regime(
            parse_number(row.get("overall_memory_prosperity_score"))
        )
    return overall_rows


def _category_cycle_summary(rows: list[dict[str, object]]) -> dict[str, object]:
    scores: list[tuple[float, float]] = []
    positive_share = 0.0
    valid_share = 0.0
    positive_count = 0
    valid_count = 0
    dominant_category = ""
    dominant_share: float | None = None
    for row in rows:
        scope_share = parse_number(row.get("category_scope_export_value_share_pct"))
        if scope_share is None:
            scope_share = parse_number(row.get("category_export_value_share_pct"))
        share = max(0.0, scope_share or 0.0)
        if dominant_share is None or share > dominant_share:
            dominant_share = share
            dominant_category = str(row.get("category") or "")
        category_score = _category_cycle_score(row)
        if category_score is None:
            continue
        valid_count += 1
        valid_share += share
        scores.append((category_score, share))
        price_yoy = parse_number(row.get("unit_price_yoy_pct"))
        price_mom = parse_number(row.get("unit_price_mom_1m_pct"))
        if price_yoy is not None and price_mom is not None and price_yoy > 0 and price_mom > 0:
            positive_count += 1
            positive_share += share

    cycle_score = _weighted_or_equal_average(scores) if 95.0 <= valid_share <= 100.000001 else None
    return {
        "category_unit_value_cycle_score": cycle_score,
        "category_breadth_score": cycle_score,  # Deprecated schema alias, not breadth.
        "category_signal_coverage_pct": valid_share,
        "category_positive_share_pct": positive_share if cycle_score is not None else None,
        "category_positive_count": positive_count,
        "category_valid_count": valid_count,
        "dominant_category": dominant_category,
        "dominant_category_share_pct": dominant_share,
    }


def _category_cycle_score(row: dict[str, object]) -> float | None:
    yoy_component = _normalize_component(
        row.get("unit_price_yoy_pct"),
        MODEL_THRESHOLDS["unit_price_yoy_pct"],
    )
    mom_component = _normalize_component(
        row.get("unit_price_mom_1m_pct"),
        MODEL_THRESHOLDS["unit_price_mom_1m_pct"],
    )
    if yoy_component is None or mom_component is None:
        return None
    signal = yoy_component * 0.75 + mom_component * 0.25
    return _component_score(signal)


def _weighted_or_equal_average(values: list[tuple[float, float]]) -> float | None:
    if not values:
        return None
    total_weight = sum(weight for _, weight in values)
    if total_weight > 0:
        return sum(value * weight for value, weight in values) / total_weight
    return sum(value for value, _ in values) / len(values)


def _combine_overall_score(
    total_score: float | None,
    category_score: float | None,
) -> float | None:
    if total_score is None:
        return None
    if category_score is None:
        return None
    return (
        total_score * OVERALL_SCORE_WEIGHT
        + category_score * CATEGORY_CYCLE_WEIGHT
    )


def _add_overall_score_trends(rows: list[dict[str, object]]) -> None:
    rows.sort(key=lambda row: str(row.get("month", "")))
    rows_by_month = {str(row.get("month")): row for row in rows}
    for row in rows:
        month = str(row.get("month"))
        score = parse_number(row.get("overall_memory_prosperity_score"))
        if score is None:
            continue
        row["overall_memory_prosperity_3m_avg"] = _rolling_field_average(
            rows_by_month,
            month,
            "overall_memory_prosperity_score",
            3,
        )
        prior_1m = rows_by_month.get(shift_month(month, -1))
        prior_3m = rows_by_month.get(shift_month(month, -3))
        prior_1m_score = parse_number(prior_1m.get("overall_memory_prosperity_score")) if prior_1m else None
        prior_3m_score = parse_number(prior_3m.get("overall_memory_prosperity_score")) if prior_3m else None
        if prior_1m_score is not None:
            row["overall_score_mom_1m"] = score - prior_1m_score
        if prior_3m_score is not None:
            row["overall_score_mom_3m"] = score - prior_3m_score


def _rolling_field_average(
    rows_by_month: dict[str, dict[str, object]],
    month: str,
    field: str,
    window: int,
) -> float | None:
    values = []
    for offset in range(-(window - 1), 1):
        row = rows_by_month.get(shift_month(month, offset))
        value = parse_number(row.get(field)) if row else None
        if value is not None:
            values.append(value)
    if len(values) != window:
        return None
    return sum(values) / len(values)


def safe_pct(numerator: float, denominator: float) -> float | None:
    if denominator <= 0:
        return None
    return numerator / denominator * 100.0


def _normalize_component(value: object, threshold: float) -> float | None:
    number = parse_number(value)
    if number is None:
        return None
    if threshold <= 0:
        raise ValueError("threshold must be positive")
    # Smooth half-saturation avoids the old hard clipping where every reading
    # beyond a threshold became indistinguishable from a much larger shock.
    return number / (abs(number) + threshold)


def _component_score(component: float | None) -> float | None:
    if component is None:
        return None
    return max(0.0, min(100.0, 50.0 + 50.0 * component))


def _add_score_trends(rows: list[dict[str, object]]) -> None:
    rows.sort(key=lambda row: str(row.get("month", "")))
    rows_by_month = {str(row.get("month")): row for row in rows}
    for row in rows:
        month = str(row.get("month"))
        score = parse_number(row.get("memory_score"))
        if score is None:
            continue
        row["memory_score_3m_avg"] = _rolling_score_average(rows_by_month, month, 3)
        prior_1m = rows_by_month.get(shift_month(month, -1))
        prior_3m = rows_by_month.get(shift_month(month, -3))
        prior_1m_score = parse_number(prior_1m.get("memory_score")) if prior_1m else None
        prior_3m_score = parse_number(prior_3m.get("memory_score")) if prior_3m else None
        if prior_1m_score is not None:
            row["score_mom_1m"] = score - prior_1m_score
        if prior_3m_score is not None:
            row["score_mom_3m"] = score - prior_3m_score


def _rolling_score_average(
    rows_by_month: dict[str, dict[str, object]],
    month: str,
    window: int,
) -> float | None:
    scores = []
    for offset in range(-(window - 1), 1):
        row = rows_by_month.get(shift_month(month, offset))
        score = parse_number(row.get("memory_score")) if row else None
        if score is not None:
            scores.append(score)
    if len(scores) != window:
        return None
    return sum(scores) / len(scores)


def _first_value(row: dict[str, object], *keys: str) -> object:
    for key in keys:
        value = row.get(key)
        if value not in {None, ""}:
            return value
    return None


def _is_prosperity_eligible(row: dict[str, object]) -> bool:
    value = row.get("prosperity_eligible")
    if value is None:
        # Backward compatibility for manually constructed/legacy category rows.
        return str(row.get("category")) not in {
            "total_memory",
            "semiconductor_memory",
            "solid_state_media",
            "storage_devices",
            "all_tracked_storage",
        }
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y"}
