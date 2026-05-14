import unittest

from korean_memory_price.cli import resolve_end_yymm


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


if __name__ == "__main__":
    unittest.main()
