from __future__ import annotations

from dataclasses import dataclass, field

from .utils import normalize_hs_code, normalize_month, parse_number


TRADE_COLUMNS = [
    "month",
    "hs_code",
    "item_name",
    "export_value_usd",
    "export_weight_kg",
    "export_quantity",
    "quantity_unit",
    "import_value_usd",
    "import_weight_kg",
    "source",
]


@dataclass(slots=True)
class TradeRecord:
    month: str
    hs_code: str
    item_name: str = ""
    export_value_usd: float | None = None
    export_weight_kg: float | None = None
    export_quantity: float | None = None
    quantity_unit: str = ""
    import_value_usd: float | None = None
    import_weight_kg: float | None = None
    source: str = ""
    raw: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.month = normalize_month(self.month)
        self.hs_code = normalize_hs_code(self.hs_code)

    def to_row(self) -> dict[str, object]:
        return {
            "month": self.month,
            "hs_code": self.hs_code,
            "item_name": self.item_name,
            "export_value_usd": self.export_value_usd,
            "export_weight_kg": self.export_weight_kg,
            "export_quantity": self.export_quantity,
            "quantity_unit": self.quantity_unit,
            "import_value_usd": self.import_value_usd,
            "import_weight_kg": self.import_weight_kg,
            "source": self.source,
        }

    @classmethod
    def from_row(cls, row: dict[str, object]) -> "TradeRecord":
        return cls(
            month=str(row.get("month", "")),
            hs_code=str(row.get("hs_code", "")),
            item_name=str(row.get("item_name") or ""),
            export_value_usd=parse_number(row.get("export_value_usd")),
            export_weight_kg=parse_number(row.get("export_weight_kg")),
            export_quantity=parse_number(row.get("export_quantity")),
            quantity_unit=str(row.get("quantity_unit") or ""),
            import_value_usd=parse_number(row.get("import_value_usd")),
            import_weight_kg=parse_number(row.get("import_weight_kg")),
            source=str(row.get("source") or ""),
            raw=dict(row),
        )
