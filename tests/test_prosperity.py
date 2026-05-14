import unittest
from datetime import date
from tempfile import TemporaryDirectory
from pathlib import Path

from korean_memory_price.charts import render_memory_indicators_png, render_memory_score_png
from korean_memory_price.prosperity import build_prosperity_scores
from korean_memory_price.utils import current_month, latest_final_month


class ProsperityTests(unittest.TestCase):
    def test_score_model_bounds_and_regime(self):
        rows = [
            {
                "month": "2025-01",
                "export_value_yoy_pct": 50,
                "export_quantity_yoy_pct": 35,
                "unit_price_yoy_pct": 50,
                "unit_price_mom_1m_pct": 12,
                "unit_price_index": 150,
                "export_quantity_index": 120,
                "export_value_usd": 1000,
            },
            {
                "month": "2025-02",
                "export_value_yoy_pct": -50,
                "export_quantity_yoy_pct": -35,
                "unit_price_yoy_pct": -50,
                "unit_price_mom_1m_pct": -12,
                "unit_price_index": 80,
                "export_quantity_index": 90,
                "export_value_usd": 700,
            },
        ]
        scores = build_prosperity_scores(rows)
        self.assertEqual(scores[0]["memory_score"], 100.0)
        self.assertEqual(scores[0]["memory_regime"], "boom")
        self.assertEqual(scores[0]["cycle_phase"], "broad_based_boom")
        self.assertEqual(scores[0]["price_score"], 100.0)
        self.assertEqual(scores[1]["memory_score"], 0.0)
        self.assertEqual(scores[1]["memory_regime"], "downturn")
        self.assertEqual(scores[1]["score_mom_1m"], -100.0)

    def test_score_trends_use_calendar_months(self):
        rows = [
            {
                "month": "2025-01",
                "export_value_yoy_pct": 0,
                "export_quantity_yoy_pct": 0,
                "unit_price_yoy_pct": 0,
                "unit_price_mom_1m_pct": 0,
            },
            {
                "month": "2025-02",
                "export_value_yoy_pct": 50,
                "export_quantity_yoy_pct": 35,
                "unit_price_yoy_pct": 50,
                "unit_price_mom_1m_pct": 12,
            },
            {
                "month": "2025-04",
                "export_value_yoy_pct": -50,
                "export_quantity_yoy_pct": -35,
                "unit_price_yoy_pct": -50,
                "unit_price_mom_1m_pct": -12,
            },
        ]
        scores = build_prosperity_scores(rows)
        self.assertEqual(scores[0]["memory_score"], 50.0)
        self.assertEqual(scores[1]["score_mom_1m"], 50.0)
        self.assertIsNone(scores[2]["score_mom_1m"])
        self.assertEqual(scores[2]["score_mom_3m"], -50.0)

    def test_latest_final_month(self):
        self.assertEqual(latest_final_month(date(2026, 5, 14)), "202603")
        self.assertEqual(latest_final_month(date(2026, 5, 16)), "202604")
        self.assertEqual(current_month(date(2026, 5, 14)), "2026-05")

    def test_chart_renderers_write_png(self):
        rows = [
            {
                "month": "2025-01",
                "export_value_yoy_pct": 10,
                "export_quantity_yoy_pct": 5,
                "unit_price_yoy_pct": 4,
                "unit_price_mom_1m_pct": 2,
                "memory_score": 62,
            },
            {
                "month": "2025-02",
                "export_value_yoy_pct": 20,
                "export_quantity_yoy_pct": 8,
                "unit_price_yoy_pct": 12,
                "unit_price_mom_1m_pct": 3,
                "memory_score": 70,
            },
        ]
        with TemporaryDirectory() as temp_dir:
            indicator_path = Path(temp_dir) / "indicators.png"
            score_path = Path(temp_dir) / "score.png"
            render_memory_indicators_png(rows, indicator_path)
            render_memory_score_png(rows, score_path)
            self.assertEqual(indicator_path.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")
            self.assertEqual(score_path.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")


if __name__ == "__main__":
    unittest.main()
