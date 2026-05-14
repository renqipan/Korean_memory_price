from __future__ import annotations

import html
from pathlib import Path

from .utils import ensure_parent, parse_number


PALETTE = {
    "export_value_yoy_pct": "#0f766e",
    "export_quantity_yoy_pct": "#2563eb",
    "unit_price_yoy_pct": "#b45309",
    "unit_price_mom_1m_pct": "#7c3aed",
    "memory_score": "#111827",
    "memory_score_3m_avg": "#dc2626",
}


def render_memory_indicators_svg(rows: list[dict[str, object]], path: str | Path) -> None:
    series = [
        ("export_value_yoy_pct", "export value YoY"),
        ("export_quantity_yoy_pct", "export quantity YoY"),
        ("unit_price_yoy_pct", "unit price YoY"),
        ("unit_price_mom_1m_pct", "unit price MoM"),
    ]
    _render_line_chart(
        rows=rows,
        series=series,
        path=path,
        title="Korean Memory Prosperity Indicators",
        y_label="percent",
        zero_line=True,
    )


def render_memory_score_svg(
    rows: list[dict[str, object]],
    path: str | Path,
) -> None:
    series = [
        ("memory_score", "memory score"),
        ("memory_score_3m_avg", "3m average"),
    ]
    _render_line_chart(
        rows=rows,
        series=series,
        path=path,
        title="Korean Memory Prosperity Score",
        y_label="score",
        zero_line=False,
        y_min=0.0,
        y_max=100.0,
    )


def _render_line_chart(
    rows: list[dict[str, object]],
    series: list[tuple[str, str]],
    path: str | Path,
    title: str,
    y_label: str,
    zero_line: bool,
    y_min: float | None = None,
    y_max: float | None = None,
) -> None:
    rows = sorted(rows, key=lambda item: str(item.get("month", "")))
    months = [str(row.get("month", "")) for row in rows]
    values = [
        value
        for row in rows
        for key, _ in series
        for value in [parse_number(row.get(key))]
        if value is not None
    ]
    if not months or not values:
        _write_empty_svg(path, title)
        return

    width = 1120
    height = 620
    left = 78
    right = 34
    top = 72
    bottom = 92
    plot_width = width - left - right
    plot_height = height - top - bottom

    low = min(values)
    high = max(values)
    if zero_line:
        low = min(low, 0.0)
        high = max(high, 0.0)
    if y_min is not None:
        low = min(low, y_min)
    if y_max is not None:
        high = max(high, y_max)
    if low == high:
        low -= 1.0
        high += 1.0
    padding = (high - low) * 0.08
    low -= padding
    high += padding

    def x_pos(index: int) -> float:
        if len(months) == 1:
            return left + plot_width / 2
        return left + plot_width * index / (len(months) - 1)

    def y_pos(value: float) -> float:
        return top + (high - value) / (high - low) * plot_height

    svg: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        f'<text x="{left}" y="38" font-family="Arial, sans-serif" font-size="24" font-weight="700" fill="#111827">{html.escape(title)}</text>',
        f'<text x="{left}" y="60" font-family="Arial, sans-serif" font-size="13" fill="#6b7280">Source: KCS/TRASS derived metrics</text>',
    ]

    for tick in _nice_ticks(low, high, 5):
        y = y_pos(tick)
        color = "#9ca3af" if abs(tick) < 1e-9 else "#e5e7eb"
        svg.append(f'<line x1="{left}" y1="{y:.2f}" x2="{left + plot_width}" y2="{y:.2f}" stroke="{color}" stroke-width="1"/>')
        svg.append(f'<text x="{left - 10}" y="{y + 4:.2f}" text-anchor="end" font-family="Arial, sans-serif" font-size="12" fill="#6b7280">{_fmt_tick(tick)}</text>')

    svg.append(f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_height}" stroke="#d1d5db"/>')
    svg.append(f'<line x1="{left}" y1="{top + plot_height}" x2="{left + plot_width}" y2="{top + plot_height}" stroke="#d1d5db"/>')
    svg.append(f'<text x="22" y="{top + plot_height / 2}" transform="rotate(-90 22 {top + plot_height / 2})" font-family="Arial, sans-serif" font-size="12" fill="#6b7280">{html.escape(y_label)}</text>')

    label_every = max(1, len(months) // 8)
    for idx, month in enumerate(months):
        if idx % label_every == 0 or idx == len(months) - 1:
            x = x_pos(idx)
            svg.append(f'<text x="{x:.2f}" y="{height - 46}" text-anchor="middle" font-family="Arial, sans-serif" font-size="12" fill="#6b7280">{html.escape(month)}</text>')

    for key, label in series:
        points = []
        for idx, row in enumerate(rows):
            value = parse_number(row.get(key))
            if value is None:
                continue
            points.append(f"{x_pos(idx):.2f},{y_pos(value):.2f}")
        if not points:
            continue
        color = PALETTE.get(key, "#374151")
        svg.append(f'<polyline points="{" ".join(points)}" fill="none" stroke="{color}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>')

    legend_x = left
    legend_y = height - 24
    for key, label in series:
        color = PALETTE.get(key, "#374151")
        svg.append(f'<line x1="{legend_x}" y1="{legend_y}" x2="{legend_x + 22}" y2="{legend_y}" stroke="{color}" stroke-width="4" stroke-linecap="round"/>')
        svg.append(f'<text x="{legend_x + 30}" y="{legend_y + 4}" font-family="Arial, sans-serif" font-size="13" fill="#374151">{html.escape(label)}</text>')
        legend_x += 220

    svg.append("</svg>")
    ensure_parent(path)
    Path(path).write_text("\n".join(svg), encoding="utf-8")


def _write_empty_svg(path: str | Path, title: str) -> None:
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="920" height="360" viewBox="0 0 920 360">
<rect width="100%" height="100%" fill="#ffffff"/>
<text x="48" y="56" font-family="Arial, sans-serif" font-size="24" font-weight="700" fill="#111827">{html.escape(title)}</text>
<text x="48" y="96" font-family="Arial, sans-serif" font-size="15" fill="#6b7280">No plottable data yet.</text>
</svg>"""
    ensure_parent(path)
    Path(path).write_text(svg, encoding="utf-8")


def _nice_ticks(low: float, high: float, count: int) -> list[float]:
    if count <= 1:
        return [low, high]
    step = (high - low) / (count - 1)
    return [low + step * idx for idx in range(count)]


def _fmt_tick(value: float) -> str:
    if abs(value) >= 100:
        return f"{value:.0f}"
    if abs(value) >= 10:
        return f"{value:.1f}"
    return f"{value:.2f}"
