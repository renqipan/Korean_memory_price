from __future__ import annotations

import csv
import re
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

from .models import TradeRecord
from .utils import normalize_hs_code, normalize_month, parse_number


HEADER_ALIASES = {
    "month": {
        "year",
        "period",
        "date",
        "yyyymm",
        "기간",
        "년월",
        "월",
        "일자",
    },
    "hs_code": {
        "hscode",
        "hs",
        "hsk",
        "hskcode",
        "품목코드",
        "품목번호",
        "hs코드",
        "hs부호",
        "세번",
    },
    "item_name": {
        "item",
        "itemname",
        "product",
        "description",
        "품목명",
        "품명",
    },
    "export_value_usd": {
        "exportamount",
        "exportvalue",
        "expdlr",
        "수출금액",
        "수출액",
    },
    "export_weight_kg": {
        "exportweight",
        "expwgt",
        "수출중량",
        "중량",
        "순중량",
    },
    "export_quantity": {
        "exportquantity",
        "quantity",
        "qty",
        "수출수량",
        "수량",
    },
    "quantity_unit": {
        "unit",
        "quantityunit",
        "수량단위",
        "단위",
    },
    "import_value_usd": {
        "importamount",
        "importvalue",
        "impdlr",
        "수입금액",
        "수입액",
    },
    "import_weight_kg": {
        "importweight",
        "impwgt",
        "수입중량",
    },
}


def load_trass_export(path: str | Path) -> list[TradeRecord]:
    path = Path(path)
    table = _read_table(path)
    if not table:
        return []
    header_index = _guess_header_index(table)
    headers = [str(cell).strip() for cell in table[header_index]]
    column_map = _build_column_map(headers)
    required = {"month", "hs_code", "export_value_usd"}
    if not required.issubset(column_map):
        raise ValueError(f"TRASS export missing required columns: {sorted(required - column_map.keys())}")
    if "export_weight_kg" not in column_map and not {"export_quantity", "quantity_unit"}.issubset(column_map):
        raise ValueError("TRASS export requires weight or quantity with an explicit unit")
    records: list[TradeRecord] = []
    for row_number, values in enumerate(table[header_index + 1 :], header_index + 2):
        row = {headers[idx]: values[idx] if idx < len(values) else "" for idx in range(len(headers))}
        if not any(str(value).strip() for value in values):
            continue
        if str(row.get(column_map["month"], "")).strip().lower() in {"total", "총계", "합계"}:
            continue
        try:
            record = _record_from_trass_row(row, column_map, path.name)
        except ValueError as exc:
            raise ValueError(f"TRASS row {row_number}: {exc}") from exc
        if record:
            records.append(record)
    if not records:
        raise ValueError("TRASS export contains no usable trade records")
    return records


def _record_from_trass_row(
    row: dict[str, object],
    column_map: dict[str, str],
    source_name: str,
) -> TradeRecord | None:
    if "month" not in column_map or "hs_code" not in column_map:
        raise ValueError("TRASS export needs at least month and HS code columns")
    month = normalize_month(row.get(column_map["month"]))
    hs_code = normalize_hs_code(row.get(column_map["hs_code"]))
    if not hs_code:
        raise ValueError("Missing HS code")

    value_header = column_map.get("export_value_usd")
    weight_header = column_map.get("export_weight_kg")
    import_value_header = column_map.get("import_value_usd")
    import_weight_header = column_map.get("import_weight_kg")

    export_value = parse_number(row.get(value_header)) if value_header else None
    export_weight = parse_number(row.get(weight_header)) if weight_header else None
    if export_value is None or export_value < 0:
        raise ValueError("Export value must be a finite, nonnegative number")
    import_value = parse_number(row.get(import_value_header)) if import_value_header else None
    import_weight = parse_number(row.get(import_weight_header)) if import_weight_header else None

    if export_value is not None and value_header and _is_thousand_usd_header(value_header):
        export_value *= 1000.0
    if import_value is not None and import_value_header and _is_thousand_usd_header(import_value_header):
        import_value *= 1000.0
    if export_weight is not None and weight_header and _is_ton_header(weight_header):
        export_weight *= 1000.0
    if import_weight is not None and import_weight_header and _is_ton_header(import_weight_header):
        import_weight *= 1000.0

    quantity_header = column_map.get("export_quantity")
    quantity_unit_header = column_map.get("quantity_unit")
    return TradeRecord(
        month=month,
        hs_code=hs_code,
        item_name=str(row.get(column_map.get("item_name", ""), "") or ""),
        export_value_usd=export_value,
        export_weight_kg=export_weight,
        export_quantity=parse_number(row.get(quantity_header)) if quantity_header else None,
        quantity_unit=str(row.get(quantity_unit_header, "") or ""),
        import_value_usd=import_value,
        import_weight_kg=import_weight,
        source=f"trass:{source_name}",
        raw=dict(row),
    )


def _read_table(path: Path) -> list[list[object]]:
    suffix = path.suffix.lower()
    if suffix in {".csv", ".txt", ".tsv"}:
        return _read_csv_table(path)
    if suffix == ".xlsx":
        return _read_xlsx_first_sheet(path)
    raise ValueError(f"unsupported TRASS export type: {path.suffix}")


def _read_csv_table(path: Path) -> list[list[str]]:
    text = path.read_text(encoding="utf-8-sig")
    dialect_probe = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(dialect_probe)
    except csv.Error:
        dialect = csv.excel_tab if path.suffix.lower() == ".tsv" else csv.excel
    return list(csv.reader(text.splitlines(), dialect))


def _read_xlsx_first_sheet(path: Path) -> list[list[object]]:
    with zipfile.ZipFile(path) as archive:
        shared_strings = _read_shared_strings(archive)
        sheet_name = _first_sheet_path(archive)
        with archive.open(sheet_name) as handle:
            root = ET.parse(handle).getroot()
    rows: list[list[object]] = []
    ns = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    for row_element in root.findall(".//x:sheetData/x:row", ns):
        row_values: list[object] = []
        for cell in row_element.findall("x:c", ns):
            col_index = _excel_col_index(cell.attrib.get("r", "A1"))
            while len(row_values) < col_index:
                row_values.append("")
            row_values.append(_xlsx_cell_value(cell, shared_strings, ns))
        rows.append(row_values)
    return rows


def _read_shared_strings(archive: zipfile.ZipFile) -> list[str]:
    try:
        with archive.open("xl/sharedStrings.xml") as handle:
            root = ET.parse(handle).getroot()
    except KeyError:
        return []
    ns = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    values: list[str] = []
    for item in root.findall("x:si", ns):
        texts = [node.text or "" for node in item.findall(".//x:t", ns)]
        values.append("".join(texts))
    return values


def _first_sheet_path(archive: zipfile.ZipFile) -> str:
    sheet_paths = sorted(
        name for name in archive.namelist() if name.startswith("xl/worksheets/sheet") and name.endswith(".xml")
    )
    if not sheet_paths:
        raise ValueError("xlsx file has no worksheets")
    return sheet_paths[0]


def _xlsx_cell_value(cell: ET.Element, shared_strings: list[str], ns: dict[str, str]) -> object:
    cell_type = cell.attrib.get("t")
    if cell_type == "inlineStr":
        texts = [node.text or "" for node in cell.findall(".//x:t", ns)]
        return "".join(texts)
    value_node = cell.find("x:v", ns)
    if value_node is None or value_node.text is None:
        return ""
    raw = value_node.text
    if cell_type == "s":
        index = int(raw)
        return shared_strings[index] if index < len(shared_strings) else ""
    # Identifiers must not acquire a '.0' suffix through float conversion.
    return raw


def _excel_col_index(cell_ref: str) -> int:
    letters = re.sub(r"[^A-Z]", "", cell_ref.upper())
    value = 0
    for letter in letters:
        value = value * 26 + (ord(letter) - ord("A") + 1)
    return max(value - 1, 0)


def _guess_header_index(table: list[list[object]]) -> int:
    best_index = 0
    best_score = -1
    for idx, row in enumerate(table[:20]):
        normalized = {_normalize_header(cell) for cell in row}
        score = sum(
            1 for aliases in HEADER_ALIASES.values() if any(alias in normalized for alias in aliases)
        )
        if score > best_score:
            best_score = score
            best_index = idx
    return best_index


def _build_column_map(headers: list[str]) -> dict[str, str]:
    column_map: dict[str, str] = {}
    for header in headers:
        normalized = _normalize_header(header)
        for canonical, aliases in HEADER_ALIASES.items():
            if normalized in aliases and canonical not in column_map:
                column_map[canonical] = header
    return column_map


def _normalize_header(value: object) -> str:
    text = str(value).strip().lower()
    # Only known measurement annotations may be stripped; unknown units fail
    # the required-column validation instead of silently changing the scale.
    text = re.sub(
        r"[\(\[]\s*(?:usd|us\$|\$|kg|kilograms?|tons?|tonnes?|톤|kg|천달러|천불|달러|thousand\s+usd|1,000\s*usd)\s*[\)\]]",
        "", text,
    )
    return re.sub(r"[\s_\-./(){}\[\],:$]+", "", text)


def _is_thousand_usd_header(header: str) -> bool:
    lowered = header.lower()
    return "천" in header or "thousand" in lowered or "1,000" in header


def _is_ton_header(header: str) -> bool:
    lowered = header.lower()
    return "톤" in header or "ton" in lowered
