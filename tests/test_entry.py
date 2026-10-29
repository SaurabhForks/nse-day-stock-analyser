import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _load import load, FIX

mod = load("trader-entry", "entry")


class TestEntry(unittest.TestCase):
    def setUp(self):
        # 7 bars for Indian 09:15 session
        self.bars = [
            {"ist_time": "09:15", "date": "2026-10-19", "high": 2505.0, "low": 2490.0, "close": 2500.0, "volume": 50000},
            {"ist_time": "09:20", "date": "2026-10-19", "high": 2510.0, "low": 2480.0, "close": 2495.0, "volume": 40000},
            {"ist_time": "09:25", "date": "2026-10-19", "high": 2508.0, "low": 2492.0, "close": 2505.0, "volume": 45000},
            {"ist_time": "09:30", "date": "2026-10-19", "high": 2509.0, "low": 2502.0, "close": 2506.0, "volume": 35000},
            {"ist_time": "09:35", "date": "2026-10-19", "high": 2508.0, "low": 2503.0, "close": 2507.0, "volume": 32000},
            {"ist_time": "09:40", "date": "2026-10-19", "high": 2511.0, "low": 2505.0, "close": 2509.0, "volume": 38000},
            {"ist_time": "09:45", "date": "2026-10-19", "high": 2520.0, "low": 2508.0, "close": 2518.0, "volume": 90000},
        ]

    def test_evaluate_orb_triggered(self):
        res = mod.evaluate_entry("RELIANCE", self.bars, setup="orb", or_minutes=15)
        self.assertEqual(res["status"], "triggered")
        self.assertEqual(res["entry_price"], 2518.0)
        self.assertEqual(res["or_high"], 2510.0)
        self.assertEqual(res["or_low"], 2480.0)
        self.assertEqual(res["trigger_bar_time"], "09:45")

    def test_evaluate_orb_waiting_inside_range(self):
        # Only bars 0..5 (no bar closes above 2510.0)
        res = mod.evaluate_entry("RELIANCE", self.bars[:6], setup="orb", or_minutes=15)
        self.assertEqual(res["status"], "waiting")

    def test_evaluate_orb_waiting_range_forming(self):
        # Only 2 bars
        res = mod.evaluate_entry("RELIANCE", self.bars[:2], setup="orb", or_minutes=15)
        self.assertEqual(res["status"], "waiting")
        self.assertIn("still forming", res["reason"])

    def test_evaluate_orb_volume_multiplier(self):
        # Avg volume of range bars: (50000 + 40000 + 45000)/3 = 45000
        # Trigger bar has 90000 vol (= 2.0x). If min_vol_x is 2.5, it should not trigger!
        res_fail = mod.evaluate_entry("RELIANCE", self.bars, setup="orb", or_minutes=15, min_vol_x=2.5)
        self.assertEqual(res_fail["status"], "waiting")

        # But min_vol_x = 1.5 triggers fine
        res_pass = mod.evaluate_entry("RELIANCE", self.bars, setup="orb", or_minutes=15, min_vol_x=1.5)
        self.assertEqual(res_pass["status"], "triggered")

    def test_evaluate_level_setup(self):
        res = mod.evaluate_entry("RELIANCE", self.bars, setup="level", level=2515.0)
        self.assertEqual(res["status"], "triggered")
        self.assertEqual(res["entry_price"], 2518.0)

    def test_evaluate_expired_at_cutoff(self):
        expired_bars = list(self.bars[:6])
        expired_bars[-1] = dict(expired_bars[-1])
        expired_bars[-1]["ist_time"] = "14:50"
        res = mod.evaluate_entry("RELIANCE", expired_bars, setup="orb", or_minutes=15, window_end="14:45")
        self.assertEqual(res["status"], "expired")

    def test_cli_check_offline(self):
        fix_chart = os.path.join(FIX, "trader-entry", "RELIANCE.json")
        rc = mod.main([
            "check", "RELIANCE", "--offline", fix_chart,
            "--now", "2026-10-19 10:15", "--no-write", "--json"
        ])
        self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()
