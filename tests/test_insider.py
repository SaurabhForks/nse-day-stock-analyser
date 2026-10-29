import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _load import load, FIX

mod = load("trader-insider", "insider")


class TestInsider(unittest.TestCase):
    def test_super_investor_lookup(self):
        damani = mod.SUPER_INVESTORS.get("damani")
        self.assertIsNotNone(damani)
        self.assertEqual(damani["name"], "Radhakishan Damani")
        self.assertTrue(any(h["symbol"] == "DMART" for h in damani["major_holdings"]))

        jhunjhunwala = mod.SUPER_INVESTORS.get("jhunjhunwala")
        self.assertIsNotNone(jhunjhunwala)
        self.assertTrue(any(h["symbol"] == "TITAN" for h in jhunjhunwala["major_holdings"]))

    def test_cli_super_investor(self):
        rc = mod.main(["super-investor", "--name", "damani", "--json"])
        self.assertEqual(rc, 0)

        rc_list = mod.main(["super-investor", "--list"])
        self.assertEqual(rc_list, 0)

    def test_cli_bulk_deals_offline(self):
        fix_dir = os.path.join(FIX, "trader-insider")
        rc = mod.main(["bulk", "--date", "2026-10-19", "--offline", fix_dir, "--json"])
        self.assertEqual(rc, 0)

    def test_cli_fii_dii(self):
        rc = mod.main(["fii-dii", "--json"])
        self.assertEqual(rc, 0)

    def test_cli_index_filings(self):
        rc = mod.main(["index", "--symbol", "RELIANCE", "--json"])
        self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()
