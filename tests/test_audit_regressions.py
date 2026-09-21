import json
import os
import unittest
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from korean_memory_price.backtest import _validation_status, build_prosperity_backtest
from korean_memory_price.charts import _render_line_chart
from korean_memory_price.cli import main
from korean_memory_price.kcs import KCSClient, KCSAPIError
from korean_memory_price.metrics import build_memory_index, build_unit_price_rows
from korean_memory_price.models import TradeRecord
from korean_memory_price.prosperity import build_overall_prosperity_index
from korean_memory_price.trass import load_trass_export
from korean_memory_price.utils import normalize_hs_code, parse_number


def observation(month, hs="8542321010", value=100, weight=10, source="kcs"):
    return TradeRecord(month, hs, export_value_usd=value, export_weight_kg=weight, source=source)


class AuditRegressionTests(unittest.TestCase):
    def test_numeric_hs_and_nonfinite_numbers(self):
        for value in [8542321010.0, "8542321010.0", "8.542321010e9", "8542.32.1010"]:
            self.assertEqual(normalize_hs_code(value), "8542321010")
        self.assertEqual(normalize_hs_code("0106191000"), "0106191000")
        for value in [float("inf"), float("nan"), "1e999"]:
            self.assertIsNone(parse_number(value))
        for value in [8542321010.5, "bad854232", "85423210100"]:
            with self.assertRaises(ValueError):
                normalize_hs_code(value)

    def test_trass_units_and_reject_unknown_units(self):
        with TemporaryDirectory() as temp:
            path = Path(temp) / "trade.csv"
            path.write_text("year,hs,Export Amount (thousand USD),Export Weight (ton)\n202601,8542321010,2,3\n")
            record = load_trass_export(path)[0]
            self.assertEqual(record.export_value_usd, 2000)
            self.assertEqual(record.export_weight_kg, 3000)
            path.write_text("year,hs,Export Amount (EUR),Export Weight (kg)\n202601,8542321010,2,3\n")
            with self.assertRaisesRegex(ValueError, "missing required columns"):
                load_trass_export(path)
            path.write_text("year,hs,exportamount,exportweight\n202601,8542321010,,3\n")
            with self.assertRaisesRegex(ValueError, "row 2"):
                load_trass_export(path)

    def test_trass_numeric_xlsx_identifier_end_to_end(self):
        xml = '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row>'
        for col, name in zip("ABCD", ["year", "hs", "exportamount", "exportweight"]):
            xml += f'<c r="{col}1" t="inlineStr"><is><t>{name}</t></is></c>'
        xml += '</row><row>'
        for col, value in zip("ABCD", ["202601", "8542321010", "100", "10"]):
            xml += f'<c r="{col}2"><v>{value}</v></c>'
        xml += '</row></sheetData></worksheet>'
        with TemporaryDirectory() as temp:
            path = Path(temp) / "trade.xlsx"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("xl/worksheets/sheet1.xml", xml)
            record = load_trass_export(path)[0]
            self.assertEqual(record.hs_code, "8542321010")
            self.assertEqual(len(build_unit_price_rows([record, observation("2026-01")])), 1)

    def test_conflicting_snapshots_and_overlapping_scopes_rejected(self):
        for records in [
            [observation("2026-01"), observation("2026-01", value=110)],
            [observation("2026-01"), observation("2026-01", value=110, source="trass")],
            [observation("2026-01"), observation("2026-01", hs="854232")],
        ]:
            with self.assertRaises(ValueError):
                build_unit_price_rows(records)

    def test_unpriced_exports_retained_and_coverage_gated(self):
        records = [observation("2025-01"), observation("2025-01", hs="8542321030"),
                   observation("2025-02"), observation("2025-02", hs="8542321030", weight=None)]
        rows = build_memory_index(build_unit_price_rows(records))
        self.assertEqual(rows[-1]["export_value_usd"], 200)
        self.assertEqual(rows[-1]["pricing_value_coverage_pct"], 50)
        self.assertEqual(rows[-1]["comparison_coverage_mom_1m_pct"], 50)
        self.assertIsNone(rows[-1]["unit_price_index"])
        self.assertIsNone(rows[-1].get("unit_price_mom_1m_pct"))

    def test_disjoint_basket_and_calendar_gap_break_chain(self):
        for records in [
            [observation("2025-01"), observation("2025-02", hs="8542321030")],
            [observation("2025-01"), observation("2025-03"), observation("2025-04")],
        ]:
            rows = build_memory_index(build_unit_price_rows(records))
            self.assertIsNone(rows[-1]["unit_price_index"])
            self.assertIn("broken", rows[-1]["index_status"])

    def test_chain_and_bilateral_growth_are_explicit(self):
        records = []
        for month, a, b in [("2024-01", 100, 100), ("2024-02", 200, 100), ("2025-01", 100, 200)]:
            records += [observation(month, value=a), observation(month, hs="8542321030", value=b)]
        rows = build_memory_index(build_unit_price_rows(records))
        self.assertEqual(rows[-1]["bilateral_unit_value_yoy_pct"], 50)
        self.assertIsNone(rows[-1]["chain_index_yoy_pct"])
        self.assertIsNone(rows[-1]["memory_index_yoy_pct"])

    def test_partial_category_coverage_cannot_produce_overall_score(self):
        result = build_overall_prosperity_index(
            [{"month": "2025-01", "memory_score": 80}],
            [{"month": "2025-01", "category": "dram", "prosperity_eligible": True,
              "unit_price_yoy_pct": 50, "unit_price_mom_1m_pct": 10,
              "category_scope_export_value_share_pct": 40}],
        )[0]
        self.assertEqual(result["category_signal_coverage_pct"], 40)
        self.assertIsNone(result["overall_memory_prosperity_score"])

    def test_backtest_needs_balanced_samples_and_baseline_advantage(self):
        self.assertEqual(_validation_status(30, .5, 80, 10, 29, 1, 10), "insufficient_sample")
        self.assertEqual(_validation_status(30, .5, 80, 10, 20, 10, -5), "mixed_internal")
        self.assertEqual(_validation_status(30, .5, 80, 10, 20, 10, 5), "supportive_internal")
        months = [f"2025-{i:02d}" for i in range(1, 5)]
        result = build_prosperity_backtest(
            [{"month": m, "unit_price_index": 100+i} for i, m in enumerate(months)],
            [{"month": m, "memory_score": s} for m, s in zip(months, [70, 30, 70, 70])], (1,),
        )[0]
        self.assertEqual(result["always_up_hit_rate_pct"], 100)
        self.assertEqual(result["contraction_sample_count"], 1)
        self.assertLess(result["excess_hit_rate_pct"], 0)

    @patch("korean_memory_price.kcs.current_month", return_value="2026-09")
    @patch.object(KCSClient, "fetch_item_trade")
    def test_latest_requires_completed_calendar_month_and_all_scopes(self, fetch, current):
        fetch.side_effect = [[observation("2026-08")], [], [observation("2026-07")], [observation("2026-07", hs="8523511000")]]
        self.assertEqual(KCSClient("test").find_latest_available_month(["854232", "852351"]), "202607")
        self.assertEqual(fetch.call_args_list[0].args[0], "202608")

    @patch.object(KCSClient, "_request_body")
    def test_response_scope_validation(self, request):
        request.return_value = '<response><item><year>2025.01</year><hsCode>8542321010</hsCode><expDlr>100</expDlr></item></response>'
        with self.assertRaises(KCSAPIError):
            KCSClient("test").fetch_item_trade("202601", "202601", "854232")

    @patch.object(KCSClient, "_request_body")
    def test_raw_snapshot_is_saved_without_request_credentials(self, request):
        request.return_value = '<response><item><year>2026.01</year><hsCode>8542321010</hsCode><expDlr>100</expDlr><expWgt>10</expWgt></item></response>'
        with TemporaryDirectory() as temp:
            KCSClient("secret-not-for-output", snapshot_dir=Path(temp)).fetch_item_trade("202601", "202601", "854232")
            snapshots = list(Path(temp).glob("*.xml"))
            self.assertEqual(len(snapshots), 1)
            self.assertEqual(snapshots[0].read_text(), request.return_value)
            self.assertNotIn("secret-not-for-output", snapshots[0].read_text())

    def test_chart_does_not_connect_missing_points(self):
        with TemporaryDirectory() as temp:
            path = Path(temp) / "chart.svg"
            _render_line_chart(rows=[{"month": "2025-01", "x": 1}, {"month": "2025-02", "x": None}, {"month": "2025-03", "x": 2}],
                               series=[("x", "test")], path=path, title="test", y_label="index", zero_line=False)
            self.assertNotIn("<polyline", path.read_text())
            self.assertEqual(path.read_text().count("<circle"), 2)

    @patch.dict(os.environ, {"DATA_GO_KR_SERVICE_KEY": "test-only"})
    @patch.object(KCSClient, "fetch_many", return_value=[observation("2026-01")])
    def test_cli_run_writes_manifest_and_price_remains_offline(self, fetch):
        with TemporaryDirectory() as temp:
            self.assertEqual(main(["run", "--start", "202601", "--end", "202601", "--outdir", temp, "--no-charts"]), 0)
            manifest = json.loads((Path(temp) / "run_manifest.json").read_text())
            self.assertEqual(manifest["publication_status"], "unverified_not_necessarily_final")
            self.assertNotIn("test-only", json.dumps(manifest))
            self.assertTrue((Path(manifest["raw_snapshot_dir"]) / "run_manifest.json").exists())
            self.assertEqual(main(["price", "--input", str(Path(temp) / "memory_trade.csv"), "--out", str(Path(temp) / "unit.csv"), "--index-out", str(Path(temp) / "index.csv")]), 0)


if __name__ == "__main__":
    unittest.main()
