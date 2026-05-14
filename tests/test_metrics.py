import unittest

from korean_memory_price.metrics import (
    build_category_memory_indexes,
    build_memory_index,
    build_unit_price_rows,
)
from korean_memory_price.categories import parse_memory_categories
from korean_memory_price.models import TradeRecord


class MetricsTests(unittest.TestCase):
    def test_unit_price_and_index(self):
        records = [
            TradeRecord(month="2024.01", hs_code="8471.70.4010", export_value_usd=1000, export_weight_kg=10),
            TradeRecord(month="2024.02", hs_code="8471.70.4010", export_value_usd=1500, export_weight_kg=10),
            TradeRecord(month="2024.01", hs_code="8542.32", export_value_usd=2000, export_weight_kg=20),
            TradeRecord(month="2024.02", hs_code="8542.32", export_value_usd=3000, export_weight_kg=20),
        ]
        unit_rows = build_unit_price_rows(records)
        self.assertEqual(unit_rows[0]["unit_usd_per_kg"], 100.0)
        index_rows = build_memory_index(unit_rows)
        self.assertEqual(len(index_rows), 2)
        self.assertEqual(round(index_rows[0]["memory_index"], 6), 100.0)
        self.assertEqual(round(index_rows[0]["unit_price_index"], 6), 100.0)
        self.assertEqual(round(index_rows[1]["memory_index"], 6), 150.0)
        self.assertEqual(round(index_rows[1]["unit_price_mom_1m_pct"], 6), 50.0)
        self.assertEqual(round(index_rows[1]["memory_index_mom_1m_pct"], 6), 50.0)

    def test_prefers_trass_quantity_without_double_counting_kcs(self):
        records = [
            TradeRecord(
                month="2024-01",
                hs_code="854232",
                export_value_usd=1000,
                export_weight_kg=10,
                source="kcs:data-go-kr",
            ),
            TradeRecord(
                month="2024-01",
                hs_code="854232",
                export_value_usd=1000,
                export_quantity=100,
                quantity_unit="EA",
                source="trass:download.csv",
            ),
            TradeRecord(
                month="2025-01",
                hs_code="854232",
                export_value_usd=1500,
                export_quantity=100,
                quantity_unit="EA",
                source="trass:download.csv",
            ),
        ]
        unit_rows = build_unit_price_rows(records)
        self.assertEqual(len(unit_rows), 2)
        self.assertTrue(all(row["source_group"] == "trass" for row in unit_rows))
        self.assertTrue(all(row["unit_price_basis"] == "EA" for row in unit_rows))

        index_rows = build_memory_index(unit_rows)
        self.assertEqual(index_rows[0]["export_value_usd"], 1000.0)
        self.assertEqual(round(index_rows[1]["unit_price_yoy_pct"], 6), 50.0)

    def test_uses_stable_hs_basis_when_quantity_is_sparse(self):
        records = [
            TradeRecord(month="2024-01", hs_code="8471704010", export_value_usd=1000, export_weight_kg=10),
            TradeRecord(month="2024-02", hs_code="8471704010", export_value_usd=1200, export_weight_kg=10),
            TradeRecord(
                month="2024-03",
                hs_code="8471704010",
                export_value_usd=1400,
                export_weight_kg=10,
                export_quantity=7,
                quantity_unit="EA",
            ),
        ]
        unit_rows = build_unit_price_rows(records)
        self.assertTrue(all(row["unit_price_basis"] == "kg" for row in unit_rows))
        self.assertEqual(unit_rows[-1]["unit_price_metric"], 140.0)

    def test_category_indexes_split_memory_segments(self):
        records = [
            TradeRecord(month="2024-01", hs_code="8542321010", export_value_usd=100, export_weight_kg=10),
            TradeRecord(month="2024-02", hs_code="8542321010", export_value_usd=200, export_weight_kg=10),
            TradeRecord(month="2024-01", hs_code="8542323000", export_value_usd=300, export_weight_kg=10),
            TradeRecord(month="2024-02", hs_code="8542323000", export_value_usd=600, export_weight_kg=10),
            TradeRecord(month="2024-01", hs_code="8542321030", export_value_usd=200, export_weight_kg=10),
            TradeRecord(month="2024-02", hs_code="8542321030", export_value_usd=300, export_weight_kg=10),
            TradeRecord(month="2024-01", hs_code="8471709000", export_value_usd=400, export_weight_kg=10),
            TradeRecord(month="2024-02", hs_code="8471709000", export_value_usd=800, export_weight_kg=10),
            TradeRecord(month="2024-01", hs_code="8542321020", export_value_usd=50, export_weight_kg=10),
            TradeRecord(month="2024-02", hs_code="8542321020", export_value_usd=50, export_weight_kg=10),
        ]
        unit_rows = build_unit_price_rows(records)
        category_rows = build_category_memory_indexes(unit_rows)
        by_category_month = {
            (row["category"], row["month"]): row
            for row in category_rows
        }

        self.assertEqual(round(by_category_month[("dram_hbm", "2024-02")]["unit_price_index"], 6), 200.0)
        self.assertEqual(round(by_category_month[("nand", "2024-02")]["unit_price_index"], 6), 150.0)
        self.assertEqual(round(by_category_month[("ssd", "2024-02")]["unit_price_index"], 6), 200.0)
        self.assertEqual(
            round(by_category_month[("total_memory", "2024-02")]["unit_price_index"], 6),
            185.714286,
        )
        self.assertEqual(
            round(by_category_month[("ssd", "2024-02")]["category_export_value_share_pct"], 6),
            41.025641,
        )
        self.assertIn("proxy", by_category_month[("ssd", "2024-02")]["category_note"])
        self.assertIn("8542321020", by_category_month[("total_memory", "2024-02")]["hs_codes"])

    def test_custom_category_replaces_default_category_key(self):
        categories = parse_memory_categories(["nand=123456"])
        by_key = {category.key: category for category in categories}
        self.assertEqual(by_key["nand"].hs_patterns, ("123456",))
        self.assertEqual(len([category for category in categories if category.key == "nand"]), 1)


if __name__ == "__main__":
    unittest.main()
