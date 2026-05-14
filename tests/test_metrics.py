import unittest

from korean_memory_price.metrics import build_memory_index, build_unit_price_rows
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


if __name__ == "__main__":
    unittest.main()
