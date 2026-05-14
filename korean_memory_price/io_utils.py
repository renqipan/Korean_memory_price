from __future__ import annotations

from pathlib import Path
from typing import Iterable

from .models import TRADE_COLUMNS, TradeRecord
from .utils import read_csv_rows, write_csv_rows


def write_trade_records(records: Iterable[TradeRecord], path: str | Path) -> None:
    rows = [record.to_row() for record in records]
    write_csv_rows(rows, path, TRADE_COLUMNS)


def read_trade_records(paths: Iterable[str | Path]) -> list[TradeRecord]:
    records: list[TradeRecord] = []
    for path in paths:
        for row in read_csv_rows(path):
            if row.get("month") and row.get("hs_code"):
                records.append(TradeRecord.from_row(row))
    return records
