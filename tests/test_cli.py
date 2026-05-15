import unittest

from korean_memory_price.cli import format_latest_category_growth_lines, resolve_end_yymm


class FakeKCSClient:
    def __init__(self):
        self.calls = []

    def find_latest_available_month(self, hs_codes, start_month=None):
        self.calls.append((tuple(hs_codes), start_month))
        return "202605"


class CLITests(unittest.TestCase):
    def test_resolve_latest_probes_kcs(self):
        client = FakeKCSClient()
        end = resolve_end_yymm("latest", client, ["854232"], "202301")
        self.assertEqual(end, "202605")
        self.assertEqual(client.calls, [(("854232",), "202301")])

    def test_resolve_explicit_month_does_not_probe(self):
        client = FakeKCSClient()
        end = resolve_end_yymm("2026-03", client, ["854232"], "202301")
        self.assertEqual(end, "202603")
        self.assertEqual(client.calls, [])

    def test_latest_category_growth_lines_use_latest_two_months(self):
        rows = [
            {
                "month": "2026-02",
                "category": "dram_hbm",
                "category_label": "DRAM/HBM",
                "unit_price_yoy_pct": 10,
                "unit_price_mom_1m_pct": 1,
            },
            {
                "month": "2026-03",
                "category": "dram_hbm",
                "category_label": "DRAM/HBM",
                "unit_price_yoy_pct": 20,
                "unit_price_mom_1m_pct": 2,
            },
            {
                "month": "2026-03",
                "category": "nand",
                "category_label": "NAND/Flash",
                "unit_price_yoy_pct": -5,
                "unit_price_mom_1m_pct": "",
            },
            {
                "month": "2026-04",
                "category": "dram_hbm",
                "category_label": "DRAM/HBM",
                "unit_price_yoy_pct": 30,
                "unit_price_mom_1m_pct": 3,
            },
            {
                "month": "2026-04",
                "category": "nand",
                "category_label": "NAND/Flash",
                "unit_price_yoy_pct": 40,
                "unit_price_mom_1m_pct": 4,
            },
            {
                "month": "2026-04",
                "category": "ssd",
                "category_label": "SSD",
                "unit_price_yoy_pct": 500,
                "unit_price_mom_1m_pct": 50,
            },
        ]
        lines = format_latest_category_growth_lines(rows)
        self.assertIn("2026-03", "\n".join(lines))
        self.assertNotIn("2026-02", "\n".join(lines))
        self.assertIn("DRAM/HBM: YoY +30.00%, MoM +3.00%", lines[-2])
        self.assertIn("NAND/Flash: YoY +40.00%, MoM +4.00%", lines[-1])
        self.assertTrue(any("NAND/Flash: YoY -5.00%, MoM N/A" in line for line in lines))


if __name__ == "__main__":
    unittest.main()
