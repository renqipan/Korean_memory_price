from __future__ import annotations

import urllib.parse
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
import time
from dataclasses import dataclass
from pathlib import Path

from .models import TradeRecord
from .utils import current_month, month_to_yymm, normalize_hs_code, parse_number, shift_month, yymm_to_month


DATA_GO_KR_ENDPOINT = "https://apis.data.go.kr/1220000/Itemtrade/getItemtradeList"
LEGACY_CUSTOMS_ENDPOINT = (
    "http://openapi.customs.go.kr/openapi/service/newTradestatistics/getitemtradeList"
)


class KCSAPIError(RuntimeError):
    """Raised when KCS returns an error response."""


@dataclass(slots=True)
class KCSClient:
    service_key: str
    endpoint: str = "data-go-kr"
    service_key_encoded: bool = False
    timeout: int = 30
    max_retries: int = 3
    retry_backoff_seconds: float = 0.5
    snapshot_dir: Path | None = None

    def fetch_item_trade(self, start_yymm: str, end_yymm: str, hs_code: str) -> list[TradeRecord]:
        hs_code = normalize_hs_code(hs_code)
        if self.endpoint == "legacy":
            url = self._build_legacy_url(start_yymm, end_yymm, hs_code)
        elif self.endpoint == "data-go-kr":
            url = self._build_data_go_kr_url(start_yymm, end_yymm, hs_code)
        else:
            raise ValueError("endpoint must be 'data-go-kr' or 'legacy'")
        request = urllib.request.Request(url, headers={"User-Agent": "korean-memory-price/0.3"})
        body = self._request_body(request)
        records = parse_item_trade_xml(body, requested_hs_code=hs_code, source=f"kcs:{self.endpoint}")
        if any(not record.hs_code.startswith(hs_code) or not start_yymm <= month_to_yymm(record.month) <= end_yymm for record in records):
            raise KCSAPIError("KCS response contains records outside the requested month or HS scope")
        if self.snapshot_dir is not None:
            self.snapshot_dir.mkdir(parents=True, exist_ok=True)
            (self.snapshot_dir / f"{hs_code}_{start_yymm}_{end_yymm}.xml").write_text(body, encoding="utf-8")
        return records

    def _request_body(self, request: urllib.request.Request) -> str:
        for attempt in range(self.max_retries + 1):
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    return response.read().decode("utf-8-sig", errors="replace")
            except urllib.error.HTTPError as exc:
                exc.close()
                retryable = exc.code == 429 or 500 <= exc.code <= 599
                if not retryable or attempt >= self.max_retries:
                    raise KCSAPIError(
                        f"KCS request failed after {attempt + 1} attempt(s): HTTP {exc.code}"
                    ) from None
            except (urllib.error.URLError, TimeoutError) as exc:
                if attempt >= self.max_retries:
                    raise KCSAPIError(
                        f"KCS network request failed after {attempt + 1} attempt(s)"
                    ) from None
            time.sleep(self.retry_backoff_seconds * (2**attempt))
        raise AssertionError("unreachable")

    def fetch_many(
        self,
        start_yymm: str,
        end_yymm: str,
        hs_codes: list[str],
    ) -> list[TradeRecord]:
        records: list[TradeRecord] = []
        for hs_code in hs_codes:
            for chunk_start, chunk_end in _iter_yymm_chunks(start_yymm, end_yymm):
                records.extend(self.fetch_item_trade(chunk_start, chunk_end, hs_code))
        return records

    def find_latest_available_month(
        self,
        hs_codes: list[str],
        start_month: str | None = None,
        lookback_months: int = 12,
    ) -> str:
        earliest = yymm_to_month(start_month) if start_month else None
        # Never compare a partial calendar month against a full prior month.
        # API availability still does not establish publication finality.
        candidate = shift_month(current_month(), -1)
        for _ in range(lookback_months):
            if earliest and candidate < earliest:
                break
            candidate_yymm = month_to_yymm(candidate)
            available = bool(hs_codes)
            for hs_code in hs_codes:
                records = self.fetch_item_trade(candidate_yymm, candidate_yymm, hs_code)
                if not _has_export_data(records):
                    available = False
                    break
            if available:
                return candidate_yymm
            candidate = shift_month(candidate, -1)
        raise KCSAPIError(
            f"No KCS export records found in the last {lookback_months} months "
            f"for HS codes: {', '.join(hs_codes)}"
        )

    def _build_data_go_kr_url(self, start_yymm: str, end_yymm: str, hs_code: str) -> str:
        params = {
            "strtYymm": start_yymm,
            "endYymm": end_yymm,
            "hsSgn": hs_code,
        }
        return self._with_service_key(DATA_GO_KR_ENDPOINT, params)

    def _build_legacy_url(self, start_yymm: str, end_yymm: str, hs_code: str) -> str:
        params = {
            "searchBgnDe": start_yymm,
            "searchEndDe": end_yymm,
            "searchItemCd": hs_code,
        }
        return self._with_service_key(LEGACY_CUSTOMS_ENDPOINT, params)

    def _with_service_key(self, base_url: str, params: dict[str, str]) -> str:
        query = urllib.parse.urlencode(params)
        if self.service_key_encoded:
            return f"{base_url}?serviceKey={self.service_key}&{query}"
        return f"{base_url}?{urllib.parse.urlencode({'serviceKey': self.service_key})}&{query}"


def parse_item_trade_xml(
    xml_text: str,
    requested_hs_code: str = "",
    source: str = "kcs",
) -> list[TradeRecord]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise KCSAPIError(f"KCS returned non-XML or malformed XML: {exc}") from exc

    result_code = _first_text(root, "resultCode")
    result_msg = _first_text(root, "resultMsg") or _first_text(root, "returnAuthMsg")
    err_msg = _first_text(root, "errMsg") or _first_text(root, "returnReasonCode")
    if result_code and result_code not in {"00", "0"}:
        message = result_msg or err_msg or "unknown KCS API error"
        raise KCSAPIError(f"KCS API error {result_code}: {message}")
    if err_msg and not _find_items(root):
        raise KCSAPIError(f"KCS API error: {err_msg}")

    records: list[TradeRecord] = []
    for item in _find_items(root):
        data = {_local_name(child.tag): (child.text or "").strip() for child in list(item)}
        if not _looks_like_trade_item(data):
            continue
        period = data.get("year") or data.get("period")
        if not period or period in {"총계", "합계", "total", "TOTAL"}:
            continue
        hs_code = data.get("hsCode") or requested_hs_code
        records.append(
            TradeRecord(
                month=period,
                hs_code=hs_code,
                item_name=data.get("statKor", ""),
                export_value_usd=parse_number(data.get("expDlr")),
                export_weight_kg=parse_number(data.get("expWgt")),
                import_value_usd=parse_number(data.get("impDlr")),
                import_weight_kg=parse_number(data.get("impWgt")),
                source=source,
                raw=data,
            )
        )
    return records


def _looks_like_trade_item(data: dict[str, str]) -> bool:
    return any(key in data for key in ("expDlr", "expWgt", "impDlr", "impWgt", "hsCode"))


def _find_items(root: ET.Element) -> list[ET.Element]:
    return [element for element in root.iter() if _local_name(element.tag) == "item"]


def _first_text(root: ET.Element, name: str) -> str | None:
    for element in root.iter():
        if _local_name(element.tag) == name and element.text:
            return element.text.strip()
    return None


def _local_name(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[1]
    return tag


def _has_export_data(records: list[TradeRecord]) -> bool:
    return any(
        (parse_number(record.export_value_usd) or 0) > 0
        and ((parse_number(record.export_weight_kg) or 0) > 0
             or ((parse_number(record.export_quantity) or 0) > 0 and bool(record.quantity_unit)))
        for record in records
    )


def _iter_yymm_chunks(
    start_yymm: str,
    end_yymm: str,
    max_months: int = 12,
) -> list[tuple[str, str]]:
    start_month = yymm_to_month(start_yymm)
    end_month = yymm_to_month(end_yymm)
    if start_month > end_month:
        raise ValueError(
            f"start month {start_yymm} must not be after end month {end_yymm}"
        )
    chunks: list[tuple[str, str]] = []
    current = start_month
    while current <= end_month:
        chunk_end = min(shift_month(current, max_months - 1), end_month)
        chunks.append((month_to_yymm(current), month_to_yymm(chunk_end)))
        current = shift_month(chunk_end, 1)
    return chunks
