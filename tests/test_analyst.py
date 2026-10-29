import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _load import load, FIX

mod = load("trader-analyst", "facts")


class TestAnalyst(unittest.TestCase):
    def test_crores_conversion(self):
        # 1 Crore = 10,000,000
        self.assertEqual(mod.to_crores(10000000), 1.0)
        self.assertEqual(mod.to_crores(185000000000), 18500.0)

    def test_parse_quarters_and_growth(self):
        fix_path = os.path.join(FIX, "trader-analyst", "financials-RELIANCE.json")
        res = mod.analyze_company("RELIANCE", offline=fix_path, num_quarters=4)

        self.assertEqual(res["symbol"], "RELIANCE")
        self.assertEqual(len(res["quarters"]), 4)

        q4 = res["quarters"][-1]
        self.assertEqual(q4["end_date"], "2026-06-30")
        self.assertEqual(q4["revenue_cr"], 251000.0)
        self.assertEqual(q4["pat_cr"], 19100.0)
        self.assertGreater(q4["ebitda_margin_pct"], 15.0)
        self.assertGreater(q4["pat_margin_pct"], 7.0)

        # TTM checks
        ttm = res["ttm"]
        self.assertGreater(ttm["revenue_cr"], 900000.0)
        self.assertGreater(ttm["pat_cr"], 70000.0)
        self.assertGreater(ttm["eps"], 100.0)

    def test_cli_facts_offline(self):
        fix_path = os.path.join(FIX, "trader-analyst", "financials-RELIANCE.json")
        rc = mod.main(["RELIANCE", "--offline", fix_path, "--json"])
        self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()
