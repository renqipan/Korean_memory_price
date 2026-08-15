import unittest

from korean_memory_price.backtest import build_prosperity_backtest


class BacktestTests(unittest.TestCase):
    def test_score_separates_subsequent_unit_value_changes(self):
        months = [f"2024-{month:02d}" for month in range(1, 13)]
        index_values = [100, 110, 120, 130, 140, 150, 160, 150, 140, 130, 120, 110]
        scores = [70] * 6 + [30] * 6
        index_rows = [
            {"month": month, "unit_price_index": value}
            for month, value in zip(months, index_values)
        ]
        prosperity_rows = [
            {"month": month, "memory_score": score}
            for month, score in zip(months, scores)
        ]

        rows = build_prosperity_backtest(index_rows, prosperity_rows, horizons=(1, 3))

        self.assertEqual([row["horizon_months"] for row in rows], [1, 3])
        self.assertGreater(rows[0]["pearson_correlation"], 0)
        self.assertGreater(rows[0]["directional_hit_rate_pct"], 80)
        self.assertGreater(rows[0]["regime_spread_pct"], 0)
        self.assertEqual(rows[0]["validation_status"], "insufficient_sample")


if __name__ == "__main__":
    unittest.main()
