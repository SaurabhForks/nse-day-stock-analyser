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

    def test_vwap_confirmation_filter(self):
        # A breakout candle with heavy upper wick rejection:
        # Spikes to high 2530 with heavy volume, but closes at 2512.
        # Typical price is (2530 + 2505 + 2512)/3 = 2515.67.
        # Close (2512.0) is > OR high (2510.0), but < VWAP (~2514.0).
        wick_rejection_bars = [
            {"ist_time": "09:15", "date": "2026-10-19", "high": 2505.0, "low": 2490.0, "close": 2500.0, "volume": 10000},
            {"ist_time": "09:20", "date": "2026-10-19", "high": 2510.0, "low": 2485.0, "close": 2495.0, "volume": 10000},
            {"ist_time": "09:25", "date": "2026-10-19", "high": 2508.0, "low": 2490.0, "close": 2505.0, "volume": 10000},
            {"ist_time": "09:30", "date": "2026-10-19", "high": 2530.0, "low": 2505.0, "close": 2512.0, "volume": 200000},
        ]
        # With require_vwap=True (default), close 2512 < VWAP 2514.4 -> blocked/waiting
        res_blocked = mod.evaluate_entry(
            "RELIANCE", wick_rejection_bars, setup="orb", or_minutes=15,
            require_vwap=True, min_close_pos=0.0, max_upper_wick=1.0
        )
        self.assertEqual(res_blocked["status"], "waiting")

        # With require_vwap=False, it triggers because close 2512 > or_high 2510
        res_allowed = mod.evaluate_entry(
            "RELIANCE", wick_rejection_bars, setup="orb", or_minutes=15,
            require_vwap=False, min_close_pos=0.0, max_upper_wick=1.0
        )
        self.assertEqual(res_allowed["status"], "triggered")
        self.assertEqual(res_allowed["entry_price"], 2512.0)

    def test_candle_upper_wick_filter(self):
        # Bar 3 has 72% upper wick (long rejection shadow)
        wick_rejection_bars = [
            {"ist_time": "09:15", "date": "2026-10-19", "high": 2505.0, "low": 2490.0, "close": 2500.0, "volume": 10000},
            {"ist_time": "09:20", "date": "2026-10-19", "high": 2510.0, "low": 2485.0, "close": 2495.0, "volume": 10000},
            {"ist_time": "09:25", "date": "2026-10-19", "high": 2508.0, "low": 2490.0, "close": 2505.0, "volume": 10000},
            {"ist_time": "09:30", "date": "2026-10-19", "high": 2530.0, "low": 2505.0, "close": 2512.0, "volume": 200000},
        ]
        # With default filter (max_upper_wick=0.35), 0.72 upper wick is rejected as waiting
        res_rej = mod.evaluate_entry("RELIANCE", wick_rejection_bars, setup="orb", or_minutes=15, require_vwap=False)
        self.assertEqual(res_rej["status"], "waiting")

        # With max_upper_wick=0.80, it triggers
        res_acc = mod.evaluate_entry("RELIANCE", wick_rejection_bars, setup="orb", or_minutes=15, require_vwap=False, min_close_pos=0.20, max_upper_wick=0.80)
        self.assertEqual(res_acc["status"], "triggered")

    def test_opening_range_width_filter(self):
        # 1. Range too narrow: OR high 2500, OR low 2498 -> 2 / 2498 = 0.08% < 0.4%
        narrow_bars = [dict(b) for b in self.bars]
        for i in range(3):
            narrow_bars[i]["high"] = 2500.0
            narrow_bars[i]["low"] = 2498.0
            narrow_bars[i]["close"] = 2499.0
        res_narrow = mod.evaluate_entry("RELIANCE", narrow_bars, setup="orb", or_minutes=15)
        self.assertEqual(res_narrow["status"], "waiting")
        self.assertIn("too narrow", res_narrow["reason"])

        # 2. Range too wide: OR high 2600, OR low 2480 -> 120 / 2480 = 4.84% > 2.0%
        wide_bars = [dict(b) for b in self.bars]
        wide_bars[0]["high"] = 2600.0
        res_wide = mod.evaluate_entry("RELIANCE", wide_bars, setup="orb", or_minutes=15)
        self.assertEqual(res_wide["status"], "waiting")
        self.assertIn("too wide", res_wide["reason"])

    def test_rvol_surge_filter(self):
        # Trigger bar volume is 90,000. Prior 5 bars average is 38,000 (RVol = 2.37x).
        # If rvol_mult is required to be 3.0x, it should wait.
        res_wait = mod.evaluate_entry("RELIANCE", self.bars, setup="orb", or_minutes=15, rvol_mult=3.0)
        self.assertEqual(res_wait["status"], "waiting")

        # If rvol_mult is 2.0x, 2.37x triggers
        res_trig = mod.evaluate_entry("RELIANCE", self.bars, setup="orb", or_minutes=15, rvol_mult=2.0)
        self.assertEqual(res_trig["status"], "triggered")
        self.assertEqual(res_trig["rvol"], 2.37)

    def test_evaluate_orb_short_breakdown(self):
        # Range high 2510, Range low 2480 (range width 1.21%)
        # Breakdown bar at 09:30 drops to low 2468, close 2470 (under 2480) with high volume
        short_bars = [
            {"ist_time": "09:15", "date": "2026-10-19", "high": 2505.0, "low": 2490.0, "close": 2500.0, "volume": 50000},
            {"ist_time": "09:20", "date": "2026-10-19", "high": 2510.0, "low": 2480.0, "close": 2495.0, "volume": 40000},
            {"ist_time": "09:25", "date": "2026-10-19", "high": 2508.0, "low": 2492.0, "close": 2505.0, "volume": 45000},
            {"ist_time": "09:30", "date": "2026-10-19", "high": 2482.0, "low": 2468.0, "close": 2470.0, "volume": 90000},
        ]
        res = mod.evaluate_entry("RELIANCE", short_bars, setup="orb", direction="short", or_minutes=15)
        self.assertEqual(res["status"], "triggered")
        self.assertEqual(res["side"], "sell")
        self.assertEqual(res["direction"], "short")
        self.assertEqual(res["entry_price"], 2470.0)
        self.assertEqual(res["or_low"], 2480.0)


if __name__ == "__main__":
    unittest.main()
