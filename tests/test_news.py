import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _load import load, FIX

mod = load("trader-news", "news")


class TestNews(unittest.TestCase):
    def test_tag_headline(self):
        tags_results = mod.tag_headline("Reliance Q2 Results: Net Profit Rises 12% to Rs 18,500 Crore")
        self.assertIn("results", tags_results)

        tags_orders = mod.tag_headline("Tata Motors Bags Rs 2,500 Crore Electric Bus Order")
        self.assertIn("orders", tags_orders)

        tags_corp = mod.tag_headline("TCS Board Recommends Interim Dividend of Rs 10 Per Share")
        self.assertIn("corporate_action", tags_corp)

        tags_reg = mod.tag_headline("SEBI Issues Show Cause Notice in Market Manipulation Probe")
        self.assertIn("regulatory", tags_reg)

    def test_parse_rss_items(self):
        rss_path = os.path.join(FIX, "trader-news", "yahoo-RELIANCE.xml")
        with open(rss_path, "rb") as f:
            items = mod.parse_rss_items(f.read(), "RELIANCE")
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["symbol"], "RELIANCE")
        self.assertIn("results", items[0]["tags"])
        self.assertIn("orders", items[1]["tags"])

    def test_get_stock_move_offline(self):
        fix_dir = os.path.join(FIX, "trader-news")
        m = mod.get_stock_move("RELIANCE", offline=fix_dir)
        self.assertIsNotNone(m)
        self.assertIn("price", m)
        self.assertIn("change_pct", m)
        self.assertGreater(m["price"], 0)

    def test_cli_news_offline(self):
        fix_dir = os.path.join(FIX, "trader-news")
        rc = mod.main([
            "--tickers", "RELIANCE", "--offline", fix_dir,
            "--all", "--no-write", "--json"
        ])
        self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()
