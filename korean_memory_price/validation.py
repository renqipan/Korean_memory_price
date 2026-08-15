from __future__ import annotations

from collections import defaultdict
from math import sqrt

from .utils import parse_number, shift_month


EXTERNAL_VALIDATION_COLUMNS = [
    "benchmark_key",
    "benchmark_label",
    "benchmark_type",
    "project_category",
    "sample_count",
    "first_month",
    "last_month",
    "pearson_correlation",
    "directional_agreement_pct",
    "level_mape_pct",
    "project_change_pct",
    "benchmark_change_pct",
    "validation_status",
    "interpretation",
    "source_url",
]


def build_external_validation(
    category_rows: list[dict[str, object]],
    benchmark_rows: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Compare project output with independently published benchmark series.

    Export-value benchmarks reconcile classification and API aggregation.
    Market-price benchmarks only test whether export unit values behave as a
    useful proxy; they are not treated as the same economic measurement.
    """
    project_by_category_month = {
        (str(row.get("category")), str(row.get("month"))): row
        for row in category_rows
        if row.get("category") and row.get("month")
    }
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in benchmark_rows:
        key = str(row.get("benchmark_key") or "").strip()
        if key:
            grouped[key].append(dict(row))

    results: list[dict[str, object]] = []
    for benchmark_key, source_rows in sorted(grouped.items()):
        source_rows.sort(key=lambda row: str(row.get("month", "")))
        first = source_rows[0]
        benchmark_type = str(first.get("benchmark_type") or "").strip()
        category = str(first.get("project_category") or "").strip()
        if benchmark_type not in {"export_value_usd", "market_price"}:
            raise ValueError(
                f"Unsupported benchmark_type {benchmark_type!r} for {benchmark_key!r}."
            )
        if any(
            str(row.get("benchmark_type") or "").strip() != benchmark_type
            or str(row.get("project_category") or "").strip() != category
            for row in source_rows
        ):
            raise ValueError(
                f"Benchmark {benchmark_key!r} mixes types or project categories."
            )
        project_field = (
            "export_value_usd"
            if benchmark_type == "export_value_usd"
            else "unit_price_index"
        )
        pairs: list[tuple[str, float, float]] = []
        for benchmark_row in source_rows:
            month = str(benchmark_row.get("month") or "").strip()
            benchmark_value = parse_number(benchmark_row.get("value"))
            project_value = parse_number(
                project_by_category_month.get((category, month), {}).get(project_field)
            )
            if month and benchmark_value is not None and project_value is not None:
                pairs.append((month, project_value, benchmark_value))

        project_values = [project for _, project, _ in pairs]
        benchmark_values = [benchmark for _, _, benchmark in pairs]
        correlation = _pearson(project_values, benchmark_values)
        directional_agreement = _directional_agreement(pairs)
        level_mape = (
            _mape(project_values, benchmark_values)
            if benchmark_type == "export_value_usd"
            else None
        )
        project_change = _total_change(project_values)
        benchmark_change = _total_change(benchmark_values)
        status = _validation_status(
            benchmark_type,
            len(pairs),
            correlation,
            directional_agreement,
            level_mape,
        )
        results.append(
            {
                "benchmark_key": benchmark_key,
                "benchmark_label": first.get("benchmark_label"),
                "benchmark_type": benchmark_type,
                "project_category": category,
                "sample_count": len(pairs),
                "first_month": pairs[0][0] if pairs else "",
                "last_month": pairs[-1][0] if pairs else "",
                "pearson_correlation": correlation,
                "directional_agreement_pct": directional_agreement,
                "level_mape_pct": level_mape,
                "project_change_pct": project_change,
                "benchmark_change_pct": benchmark_change,
                "validation_status": status,
                "interpretation": _interpretation(benchmark_type, status),
                "source_url": first.get("source_url"),
            }
        )
    return results


def _pearson(left: list[float], right: list[float]) -> float | None:
    if len(left) != len(right) or len(left) < 3:
        return None
    left_mean = sum(left) / len(left)
    right_mean = sum(right) / len(right)
    covariance = sum(
        (left_value - left_mean) * (right_value - right_mean)
        for left_value, right_value in zip(left, right)
    )
    denominator = sqrt(
        sum((value - left_mean) ** 2 for value in left)
        * sum((value - right_mean) ** 2 for value in right)
    )
    return covariance / denominator if denominator else None


def _directional_agreement(pairs: list[tuple[str, float, float]]) -> float | None:
    if len(pairs) < 2:
        return None
    matches = 0
    comparisons = 0
    for (prior_month, prior_project, prior_benchmark), (month, project, benchmark) in zip(
        pairs, pairs[1:]
    ):
        if month != shift_month(prior_month, 1):
            continue
        project_change = project - prior_project
        benchmark_change = benchmark - prior_benchmark
        if project_change == 0 and benchmark_change == 0:
            matches += 1
        elif project_change * benchmark_change > 0:
            matches += 1
        comparisons += 1
    return matches / comparisons * 100.0 if comparisons else None


def _mape(project: list[float], benchmark: list[float]) -> float | None:
    errors = [
        abs(project_value - benchmark_value) / abs(benchmark_value)
        for project_value, benchmark_value in zip(project, benchmark)
        if benchmark_value != 0
    ]
    return sum(errors) / len(errors) * 100.0 if errors else None


def _total_change(values: list[float]) -> float | None:
    if len(values) < 2 or values[0] == 0:
        return None
    return (values[-1] / values[0] - 1.0) * 100.0


def _validation_status(
    benchmark_type: str,
    sample_count: int,
    correlation: float | None,
    directional_agreement: float | None,
    level_mape: float | None,
) -> str:
    if sample_count < 3:
        return "insufficient_sample"
    if benchmark_type == "export_value_usd":
        if level_mape is not None and level_mape <= 2.0:
            return "aligned"
        if level_mape is not None and level_mape <= 10.0:
            return "close"
        return "mismatch"
    if correlation is None or directional_agreement is None:
        return "insufficient_sample"
    if correlation >= 0.70 and directional_agreement >= 60.0:
        return "strong_proxy"
    if correlation >= 0.50 and directional_agreement >= 50.0:
        return "moderate_proxy"
    return "weak_proxy"


def _interpretation(benchmark_type: str, status: str) -> str:
    if benchmark_type == "export_value_usd":
        return {
            "aligned": "Project export values reconcile with the rounded official series.",
            "close": "Project export values are close but need classification review.",
            "mismatch": "Project export values do not reconcile with the official series.",
            "insufficient_sample": "Too few overlapping months for reconciliation.",
        }[status]
    return {
        "strong_proxy": "Export unit value is a strong proxy over this sample, not the same price series.",
        "moderate_proxy": "Export unit value is a moderate proxy over this sample; use market prices separately.",
        "weak_proxy": "Export unit value is a weak market-price proxy over this sample.",
        "insufficient_sample": "Too few overlapping months for proxy assessment.",
    }[status]
