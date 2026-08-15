import unittest
import urllib.error
from unittest.mock import MagicMock, patch

from korean_memory_price.kcs import KCSClient, _iter_yymm_chunks, parse_item_trade_xml


SAMPLE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<response>
  <header>
    <resultCode>00</resultCode>
    <resultMsg>NORMAL SERVICE.</resultMsg>
  </header>
  <body>
    <items>
      <item>
        <balPayments>-174254</balPayments>
        <expDlr>94676</expDlr>
        <expWgt>5610</expWgt>
        <hsCode>0106191000</hsCode>
        <impDlr>268930</impDlr>
        <impWgt>2847</impWgt>
        <statKor>memory item</statKor>
        <year>2017.01</year>
      </item>
      <item>
        <balPayments>-174254</balPayments>
        <expDlr>94676</expDlr>
        <expWgt>5610</expWgt>
        <hsCode>-</hsCode>
        <impDlr>268930</impDlr>
        <impWgt>2847</impWgt>
        <statKor>-</statKor>
        <year>총계</year>
      </item>
    </items>
  </body>
</response>
"""


class KCSParserTests(unittest.TestCase):
    def test_parse_item_trade_xml_skips_total(self):
        records = parse_item_trade_xml(SAMPLE_XML)
        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record.month, "2017-01")
        self.assertEqual(record.hs_code, "0106191000")
        self.assertEqual(record.export_value_usd, 94676.0)
        self.assertEqual(record.export_weight_kg, 5610.0)

    def test_iter_yymm_chunks_limits_long_requests(self):
        chunks = _iter_yymm_chunks("202301", "202603")
        self.assertEqual(chunks[0], ("202301", "202312"))
        self.assertEqual(chunks[1], ("202401", "202412"))
        self.assertEqual(chunks[-1], ("202601", "202603"))

    def test_iter_yymm_chunks_rejects_reversed_range(self):
        with self.assertRaisesRegex(ValueError, "must not be after"):
            _iter_yymm_chunks("202603", "202301")

    @patch("korean_memory_price.kcs.time.sleep")
    @patch("korean_memory_price.kcs.urllib.request.urlopen")
    def test_transient_http_error_is_retried(self, urlopen, sleep):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = SAMPLE_XML.encode()
        urlopen.side_effect = [
            urllib.error.HTTPError("https://example.test", 502, "bad gateway", {}, None),
            response,
        ]
        client = KCSClient(
            service_key="test",
            max_retries=2,
            retry_backoff_seconds=0.01,
        )

        records = client.fetch_item_trade("202401", "202401", "854232")

        self.assertEqual(len(records), 1)
        self.assertEqual(urlopen.call_count, 2)
        sleep.assert_called_once_with(0.01)


if __name__ == "__main__":
    unittest.main()
