from __future__ import annotations

from math import sqrt

from .prosperity import MODEL_VERSION
from .utils import parse_number, shift_month


BACKTEST_COLUMNS = [
    "model_version",
    "target",
    "horizon_months",
    "sample_count",
    "signal_sample_count",
    "expansion_sample_count",
    "contraction_sample_count",
    "always_up_hit_rate_pct",
    "excess_hit_rate_pct",
    "pearson_correlation",
    "directional_hit_rate_pct",
    "expansion_avg_future_change_pct",
    "contraction_avg_future_change_pct",
    "regime_spread_pct",
    "validation_design",
    "validation_status",
    "first_evaluated_month",
    "last_evaluated_month",
]


def build_prosperity_backtest(
    index_rows: list[dict[str, object]],
    prosperity_rows: list[dict[str, object]],
    horizons: tuple[int, ...] = (1, 3, 6, 12),
) -> list[dict[str, object]]:
    """Evaluate whether the score separates subsequent core unit-value returns.

    This is a retrospective forward-association diagnostic: the score at month
    t is paired only with a later unit-value-index observation at t+h.  It is
    not a held-out or independently specified out-of-sample test, and future
    windows overlap for horizons longer than one month.
    """
    index_by_month = {
        str(row.get("month")): row
        for row in index_rows
        if row.get("month")
    }
    score_by_month = {
        str(row.get("month")): row
        for row in prosperity_rows
        if row.get("month")
    }
    results: list[dict[str, object]] = []
    for horizon in horizons:
        pairs: list[tuple[str, float, float]] = []
        for month in sorted(score_by_month):
            score = parse_number(score_by_month[month].get("memory_score"))
            current = parse_number(index_by_month.get(month, {}).get("unit_price_index"))
            future_month = shift_month(month, horizon)
            future = parse_number(
                index_by_month.get(future_month, {}).get("unit_price_index")
            )
            if score is None or current is None or future is None or current <= 0:
                continue
            future_change = (future / current - 1.0) * 100.0
            pairs.append((month, score, future_change))

        expansion = [future for _, score, future in pairs if score >= 60.0]
        contraction = [future for _, score, future in pairs if score < 45.0]
        directional = [
            (score >= 60.0 and future > 0.0)
            or (score < 45.0 and future < 0.0)
            for _, score, future in pairs
            if score >= 60.0 or score < 45.0
        ]
        expansion_average = _average(expansion)
        contraction_average = _average(contraction)
        correlation = _pearson(
            [score for _, score, _ in pairs],
            [future for _, _, future in pairs],
        )
        hit_rate = (
            sum(directional) / len(directional) * 100.0
            if directional
            else None
        )
        signal_futures = [future for _, score, future in pairs if score >= 60.0 or score < 45.0]
        baseline = sum(future > 0 for future in signal_futures) / len(signal_futures) * 100.0 if signal_futures else None
        excess = hit_rate - baseline if hit_rate is not None and baseline is not None else None
        spread = (
            expansion_average - contraction_average
            if expansion_average is not None and contraction_average is not None
            else None
        )
        results.append(
            {
                "model_version": MODEL_VERSION,
                "target": "future_core_unit_value_index_change_pct",
                "horizon_months": horizon,
                "sample_count": len(pairs),
                "signal_sample_count": len(directional),
                "expansion_sample_count": len(expansion),
                "contraction_sample_count": len(contraction),
                "always_up_hit_rate_pct": baseline,
                "excess_hit_rate_pct": excess,
                "pearson_correlation": correlation,
                "directional_hit_rate_pct": hit_rate,
                "expansion_avg_future_change_pct": expansion_average,
                "contraction_avg_future_change_pct": contraction_average,
                "regime_spread_pct": spread,
                "validation_design": "internal_forward_association_overlapping_horizons",
                "validation_status": _validation_status(
                    len(pairs), correlation, hit_rate, spread,
                    len(expansion), len(contraction), excess,
                ),
                "first_evaluated_month": pairs[0][0] if pairs else "",
                "last_evaluated_month": pairs[-1][0] if pairs else "",
            }
        )
    return results


def _average(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _pearson(left: list[float], right: list[float]) -> float | None:
    if len(left) != len(right) or len(left) < 3:
        return None
    left_mean = sum(left) / len(left)
    right_mean = sum(right) / len(right)
    covariance = sum(
        (left_value - left_mean) * (right_value - right_mean)
        for left_value, right_value in zip(left, right)
    )
    left_variance = sum((value - left_mean) ** 2 for value in left)
    right_variance = sum((value - right_mean) ** 2 for value in right)
    denominator = sqrt(left_variance * right_variance)
    if denominator == 0:
        return None
    return covariance / denominator


def _validation_status(
    sample_count: int,
    correlation: float | None,
    hit_rate: float | None,
    spread: float | None,
    expansion_count: int,
    contraction_count: int,
    excess_hit_rate: float | None,
) -> str:
    if sample_count < 24 or min(expansion_count, contraction_count) < 6 or correlation is None or hit_rate is None or spread is None:
        return "insufficient_sample"
    if correlation >= 0.10 and hit_rate >= 55.0 and spread > 0.0 and excess_hit_rate is not None and excess_hit_rate > 0:
        return "supportive_internal"
    return "mixed_internal"
