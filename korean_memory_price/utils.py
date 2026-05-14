from __future__ import annotations

import csv
import math
import os
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping, Sequence


def parse_number(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        if isinstance(value, float) and math.isnan(value):
            return None
        return float(value)
    text = str(value).strip()
    if not text or text in {"-", "--", "N/A", "NA", "null", "None"}:
        return None
    negative = text.startswith("(") and text.endswith(")")
    text = text.strip("()")
    text = text.replace(",", "")
    text = text.replace("$", "")
    text = text.replace("USD", "")
    text = text.replace("usd", "")
    text = text.replace("%", "")
    text = re.sub(r"[^0-9+\-.eE]", "", text)
    if text in {"", "-", "+", "."}:
        return None
    try:
        number = float(text)
    except ValueError:
        return None
    return -number if negative else number


def safe_div(numerator: object, denominator: object) -> float | None:
    num = parse_number(numerator)
    den = parse_number(denominator)
    if num is None or den is None or den == 0:
        return None
    return num / den


def pct_change(current: object, previous: object) -> float | None:
    cur = parse_number(current)
    prev = parse_number(previous)
    if cur is None or prev is None or prev == 0:
        return None
    return (cur / prev - 1.0) * 100.0


def normalize_hs_code(value: object) -> str:
    if value is None:
        return ""
    return re.sub(r"\D", "", str(value))


def normalize_month(value: object) -> str:
    if value is None:
        raise ValueError("missing month")
    text = str(value).strip()
    match = re.search(r"((?:19|20)\d{2})\D*([01]?\d)", text)
    if not match:
        raise ValueError(f"cannot parse month from {value!r}")
    year = int(match.group(1))
    month = int(match.group(2))
    if not 1 <= month <= 12:
        raise ValueError(f"invalid month in {value!r}")
    return f"{year:04d}-{month:02d}"


def month_to_yymm(month: str) -> str:
    if str(month).strip().lower() == "latest":
        return latest_final_month()
    normalized = normalize_month(month)
    return normalized.replace("-", "")


def yymm_to_month(yymm: str) -> str:
    return normalize_month(yymm)


def month_to_date(month: str) -> date:
    normalized = normalize_month(month)
    year, mon = normalized.split("-")
    return date(int(year), int(mon), 1)


def shift_month(month: str, offset: int) -> str:
    month_date = month_to_date(month)
    zero_based = month_date.year * 12 + (month_date.month - 1) + offset
    year, zero_month = divmod(zero_based, 12)
    return f"{year:04d}-{zero_month + 1:02d}"


def parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def current_month(today: date | None = None) -> str:
    today = today or date.today()
    return f"{today.year:04d}-{today.month:02d}"


def latest_final_month(today: date | None = None) -> str:
    """Return YYYYMM for the latest likely-final KCS monthly statistics.

    KCS final monthly item statistics are generally available around the 15th
    of the following month. Before the 16th, use the month before last.
    """
    today = today or date.today()
    offset = 1 if today.day >= 16 else 2
    year = today.year
    month = today.month - offset
    while month <= 0:
        month += 12
        year -= 1
    return f"{year:04d}{month:02d}"


def to_unix_seconds(day: date) -> int:
    dt = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
    return int(dt.timestamp())


def ensure_parent(path: str | os.PathLike[str]) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)


def read_csv_rows(path: str | os.PathLike[str]) -> list[dict[str, str]]:
    with open(path, newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def write_csv_rows(
    rows: Sequence[Mapping[str, object]],
    path: str | os.PathLike[str],
    fieldnames: Sequence[str] | None = None,
) -> None:
    ensure_parent(path)
    if fieldnames is None:
        seen: list[str] = []
        for row in rows:
            for key in row:
                if key not in seen:
                    seen.append(key)
        fieldnames = seen
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: format_csv_value(row.get(key)) for key in fieldnames})


def format_csv_value(value: object) -> object:
    if value is None:
        return ""
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return ""
        return f"{value:.10g}"
    return value


def pearson(xs: Iterable[object], ys: Iterable[object]) -> float | None:
    pairs = [
        (x, y)
        for x, y in zip((parse_number(x) for x in xs), (parse_number(y) for y in ys))
        if x is not None and y is not None
    ]
    if len(pairs) < 3:
        return None
    x_vals = [x for x, _ in pairs]
    y_vals = [y for _, y in pairs]
    x_mean = sum(x_vals) / len(x_vals)
    y_mean = sum(y_vals) / len(y_vals)
    x_dev = [x - x_mean for x in x_vals]
    y_dev = [y - y_mean for y in y_vals]
    numerator = sum(x * y for x, y in zip(x_dev, y_dev))
    x_var = sum(x * x for x in x_dev)
    y_var = sum(y * y for y in y_dev)
    if x_var == 0 or y_var == 0:
        return None
    return numerator / math.sqrt(x_var * y_var)


def sort_by_month(rows: list[dict[str, object]], key: str = "month") -> list[dict[str, object]]:
    return sorted(rows, key=lambda row: str(row.get(key, "")))
