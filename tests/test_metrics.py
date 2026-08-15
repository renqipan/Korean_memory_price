import unittest

from korean_memory_price.metrics import (
    build_category_memory_indexes,
    build_memory_index,
    build_unit_price_rows,
)
from korean_memory_price.categories import (
    DEFAULT_FETCH_HS_CODES,
    DEFAULT_MEMORY_CATEGORIES,
    matches_category,
    parse_memory_categories,
)
from korean_memory_price.models import TradeRecord


class MetricsTests(unittest.TestCase):
    def test_top_level_product_scopes_are_separate(self):
        top_level = [
            category
            for category in DEFAULT_MEMORY_CATEGORIES
            if category.role in {"core", "context"}
        ]
        expected = {
            "8542321010": "semiconductor_memory",
            "8523511000": "solid_state_media",
            "8471702020": "storage_devices",
        }
        for hs_code, expected_category in expected.items():
            matches = [
                category.key
                for category in top_level
                if matches_category(hs_code, category)
            ]
            self.assertEqual(matches, [expected_category])
        self.assertEqual(
            DEFAULT_FETCH_HS_CODES,
            ["854232", "8473304060", "852351", "847170"],
        )

    def test_official_ict_dram_scope_includes_ic_and_module(self):
        categories = {category.key: category for category in DEFAULT_MEMORY_CATEGORIES}
        self.assertTrue(matches_category("8542321010", categories["ict_dram"]))
        self.assertTrue(matches_category("8473304060", categories["ict_dram"]))
        self.assertFalse(matches_category("8473304060", categories["semiconductor_memory"]))
        self.assertEqual(categories["dram"].label, "DRAM IC")
        self.assertFalse(categories["dram_module"].prosperity_eligible)

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

    def test_bilateral_growth_uses_prior_export_value_weights(self):
        records = [
            TradeRecord(
                month="2024-01",
                hs_code="8542321010",
                export_value_usd=100,
                export_weight_kg=10,
            ),
            TradeRecord(
                month="2024-01",
                hs_code="8542323000",
                export_value_usd=400,
                export_weight_kg=20,
            ),
            TradeRecord(
                month="2024-02",
                hs_code="8542321010",
                export_value_usd=200,
                export_weight_kg=10,
            ),
            TradeRecord(
                month="2024-02",
                hs_code="8542323000",
                export_value_usd=200,
                export_weight_kg=20,
            ),
        ]

        index_rows = build_memory_index(build_unit_price_rows(records))

        # Price relatives are 2.0 and 0.5, weighted by prior values 100 and 400.
        self.assertAlmostEqual(index_rows[1]["unit_price_mom_1m_pct"], -20.0)
        self.assertAlmostEqual(index_rows[1]["unit_price_index"], 80.0)

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

    def test_identical_source_records_are_not_double_counted(self):
        record = TradeRecord(
            month="2024-01",
            hs_code="8542321010",
            export_value_usd=1000,
            export_weight_kg=10,
            source="kcs:data-go-kr",
        )
        duplicate = TradeRecord(
            month="2024-01",
            hs_code="8542321010",
            export_value_usd=1000,
            export_weight_kg=10,
            source="kcs:data-go-kr",
        )

        unit_rows = build_unit_price_rows([record, duplicate])

        self.assertEqual(len(unit_rows), 1)
        self.assertEqual(unit_rows[0]["export_value_usd"], 1000.0)
        self.assertEqual(unit_rows[0]["export_weight_kg"], 10.0)

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

    def test_basis_choice_does_not_depend_on_requested_history(self):
        records = [
            TradeRecord(
                month="2024-01",
                hs_code="8542321010",
                export_value_usd=100,
                export_weight_kg=10,
            ),
            TradeRecord(
                month="2024-02",
                hs_code="8542321010",
                export_value_usd=120,
                export_weight_kg=10,
                export_quantity=5,
                quantity_unit="EA",
            ),
        ]
        full = build_unit_price_rows(records)
        later = build_unit_price_rows(records[1:])
        self.assertEqual(full[-1]["unit_price_basis"], "kg")
        self.assertEqual(later[0]["unit_price_basis"], "kg")
        self.assertEqual(full[-1]["unit_price_metric"], later[0]["unit_price_metric"])

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
            TradeRecord(month="2024-01", hs_code="8523511000", export_value_usd=500, export_weight_kg=10),
            TradeRecord(month="2024-02", hs_code="8523511000", export_value_usd=550, export_weight_kg=10),
            TradeRecord(month="2024-01", hs_code="8542321020", export_value_usd=50, export_weight_kg=10),
            TradeRecord(month="2024-02", hs_code="8542321020", export_value_usd=50, export_weight_kg=10),
        ]
        unit_rows = build_unit_price_rows(records)
        category_rows = build_category_memory_indexes(unit_rows)
        by_category_month = {
            (row["category"], row["month"]): row
            for row in category_rows
        }

        self.assertEqual(round(by_category_month[("dram", "2024-02")]["unit_price_index"], 6), 200.0)
        self.assertEqual(round(by_category_month[("flash_memory", "2024-02")]["unit_price_index"], 6), 150.0)
        self.assertEqual(round(by_category_month[("storage_devices", "2024-02")]["unit_price_index"], 6), 200.0)
        self.assertEqual(round(by_category_month[("solid_state_media", "2024-02")]["unit_price_index"], 6), 110.0)
        self.assertEqual(
            round(by_category_month[("semiconductor_memory", "2024-02")]["unit_price_index"], 6),
            176.923077,
        )
        self.assertEqual(
            round(by_category_month[("storage_devices", "2024-02")]["category_export_value_share_pct"], 6),
            32.0,
        )
        self.assertEqual(
            round(by_category_month[("dram", "2024-02")]["category_scope_export_value_share_pct"], 6),
            17.391304,
        )
        self.assertTrue(by_category_month[("dram", "2024-02")]["prosperity_eligible"])
        self.assertFalse(by_category_month[("storage_devices", "2024-02")]["prosperity_eligible"])
        self.assertIn("must not be labelled as SSD", by_category_month[("storage_devices", "2024-02")]["category_note"])
        self.assertIn("8542321020", by_category_month[("semiconductor_memory", "2024-02")]["hs_codes"])

    def test_custom_category_replaces_default_category_key(self):
        categories = parse_memory_categories(["flash_memory=123456"])
        by_key = {category.key: category for category in categories}
        self.assertEqual(by_key["flash_memory"].hs_patterns, ("123456",))
        self.assertTrue(by_key["flash_memory"].prosperity_eligible)
        self.assertEqual(len([category for category in categories if category.key == "flash_memory"]), 1)

    def test_price_growth_is_independent_of_requested_start_month(self):
        records = []
        for month_number in range(1, 19):
            year = 2024 + (month_number - 1) // 12
            month = (month_number - 1) % 12 + 1
            month_label = f"{year:04d}-{month:02d}"
            records.extend(
                [
                    TradeRecord(
                        month=month_label,
                        hs_code="8542321010",
                        export_value_usd=(100 + month_number * 8) * (10 + month_number),
                        export_weight_kg=10 + month_number,
                    ),
                    TradeRecord(
                        month=month_label,
                        hs_code="8542323000",
                        export_value_usd=(300 + month_number * 3) * (40 - month_number),
                        export_weight_kg=40 - month_number,
                    ),
                ]
            )

        full_rows = build_category_memory_indexes(build_unit_price_rows(records))
        later_records = [record for record in records if record.month >= "2024-04"]
        later_rows = build_category_memory_indexes(build_unit_price_rows(later_records))
        full_latest = next(
            row for row in full_rows
            if row["category"] == "semiconductor_memory" and row["month"] == "2025-06"
        )
        later_latest = next(
            row for row in later_rows
            if row["category"] == "semiconductor_memory" and row["month"] == "2025-06"
        )

        self.assertAlmostEqual(
            full_latest["unit_price_mom_1m_pct"],
            later_latest["unit_price_mom_1m_pct"],
        )
        self.assertAlmostEqual(
            full_latest["unit_price_yoy_pct"],
            later_latest["unit_price_yoy_pct"],
        )
        self.assertEqual(
            full_latest["index_weight_method"],
            "chain_linked_prior_period_export_value",
        )


if __name__ == "__main__":
    unittest.main()
