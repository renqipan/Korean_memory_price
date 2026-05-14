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
    "score_confidence",
    "valid_indicator_count",
    "value_score",
    "volume_score",
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
    "model_version",
]


MODEL_VERSION = "memory-prosperity-v2"


MODEL_WEIGHTS = {
    "export_value_yoy_pct": 0.20,
    "export_quantity_yoy_pct": 0.25,
    "unit_price_yoy_pct": 0.35,
    "unit_price_mom_1m_pct": 0.20,
}


MODEL_THRESHOLDS = {
    "export_value_yoy_pct": 50.0,
    "export_quantity_yoy_pct": 35.0,
    "unit_price_yoy_pct": 50.0,
    "unit_price_mom_1m_pct": 12.0,
}


def build_prosperity_scores(
    index_rows: list[dict[str, object]],
    min_indicators: int = 2,
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
            if value is not None
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
                "score_confidence": len(available) / len(MODEL_WEIGHTS),
                "valid_indicator_count": len(available),
                "value_score": _component_score(components["export_value_yoy_pct"]),
                "volume_score": _component_score(components["export_quantity_yoy_pct"]),
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
        return "price_led_boom"
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


def _normalize_component(value: object, threshold: float) -> float | None:
    number = parse_number(value)
    if number is None:
        return None
    return max(-1.0, min(1.0, number / threshold))


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
    if not scores:
        return None
    return sum(scores) / len(scores)


def _first_value(row: dict[str, object], *keys: str) -> object:
    for key in keys:
        value = row.get(key)
        if value not in {None, ""}:
            return value
    return None
