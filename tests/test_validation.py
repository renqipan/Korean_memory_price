import unittest

from korean_memory_price.validation import build_external_validation


class ExternalValidationTests(unittest.TestCase):
    def test_export_value_reconciliation_and_market_proxy_are_distinct(self):
        category_rows = []
        benchmark_rows = []
        for month, export_value, unit_value, market_price in [
            ("2025-01", 100, 100, 1.0),
            ("2025-02", 200, 90, 1.2),
            ("2025-03", 300, 120, 1.4),
            ("2025-04", 400, 140, 1.6),
        ]:
            category_rows.append(
                {
                    "month": month,
                    "category": "ict_dram",
                    "export_value_usd": export_value,
                }
            )
            category_rows.append(
                {
                    "month": month,
                    "category": "dram",
                    "unit_price_index": unit_value,
                }
            )
            benchmark_rows.append(
                {
                    "month": month,
                    "benchmark_key": "official_dram",
                    "benchmark_label": "Official DRAM",
                    "benchmark_type": "export_value_usd",
                    "project_category": "ict_dram",
                    "value": export_value,
                    "source_url": "https://example.test/official",
                }
            )
            benchmark_rows.append(
                {
                    "month": month,
                    "benchmark_key": "market_dram",
                    "benchmark_label": "Market DRAM",
                    "benchmark_type": "market_price",
                    "project_category": "dram",
                    "value": market_price,
                    "source_url": "https://example.test/market",
                }
            )

        rows = {
            row["benchmark_key"]: row
            for row in build_external_validation(category_rows, benchmark_rows)
        }

        self.assertEqual(rows["official_dram"]["validation_status"], "aligned")
        self.assertEqual(rows["official_dram"]["level_mape_pct"], 0.0)
        self.assertIn(
            rows["market_dram"]["validation_status"],
            {"moderate_proxy", "strong_proxy"},
        )
        self.assertIsNone(rows["market_dram"]["level_mape_pct"])

    def test_direction_comparison_skips_calendar_gaps(self):
        category_rows = [
            {"month": "2025-01", "category": "dram", "unit_price_index": 100},
            {"month": "2025-03", "category": "dram", "unit_price_index": 200},
        ]
        benchmark_rows = [
            {
                "month": month,
                "benchmark_key": "market_dram",
                "benchmark_label": "Market DRAM",
                "benchmark_type": "market_price",
                "project_category": "dram",
                "value": value,
            }
            for month, value in [("2025-01", 1), ("2025-03", 2)]
        ]

        row = build_external_validation(category_rows, benchmark_rows)[0]

        self.assertIsNone(row["directional_agreement_pct"])
        self.assertEqual(row["validation_status"], "insufficient_sample")


if __name__ == "__main__":
    unittest.main()
