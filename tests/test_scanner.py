import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _load import load, FIX

mod = load("trader-scanner", "scan")


class TestScanner(unittest.TestCase):
    def test_filter_equity_l_universe(self):
        csv_sample = """SYMBOL,NAME OF COMPANY, SERIES, DATE OF LISTING, PAID UP VALUE
RELIANCE,Reliance Industries Limited,EQ,29-NOV-1995,10
TCS,Tata Consultancy Services Limited,EQ,25-AUG-2004,1
NIFTYBEES,Nippon India ETF Nifty 50 BeES,EQ,08-JAN-2002,1
GOLDBEES,Nippon India ETF Gold BeES,EQ,08-JAN-2002,1
SME1,Some SME Stock,SM,10-JAN-2022,10
PREF1,Some Preference Share,P1,10-JAN-2020,100
"""
        stocks = mod.filter_equity_l(csv_sample)
        symbols = [s[0] for s in stocks]
        self.assertIn("RELIANCE", symbols)
        self.assertIn("TCS", symbols)
        self.assertNotIn("NIFTYBEES", symbols)  # ETF excluded
        self.assertNotIn("GOLDBEES", symbols)   # ETF excluded
        self.assertNotIn("SME1", symbols)       # SM series excluded
        self.assertNotIn("PREF1", symbols)      # P1 series excluded

    def test_symbols_clean_and_yahoo(self):
        self.assertEqual(mod.clean_symbol("RELIANCE.NS"), "RELIANCE")
        self.assertEqual(mod.clean_symbol("TCS.BO"), "TCS")
        self.assertEqual(mod.clean_symbol("INFY"), "INFY")
        self.assertEqual(mod.yahoo_symbol("RELIANCE"), "RELIANCE.NS")
        self.assertEqual(mod.yahoo_symbol("RELIANCE.NS"), "RELIANCE.NS")

    def test_ist_calendar_and_holidays(self):
        import datetime
        republic_day = datetime.date(2026, 1, 26)
        self.assertFalse(mod.is_trading_day(republic_day))
        weekend = datetime.date(2026, 10, 18)  # Sunday
        self.assertFalse(mod.is_trading_day(weekend))
        weekday = datetime.date(2026, 10, 19)  # Monday
        self.assertTrue(mod.is_trading_day(weekday))

    def test_daily_setups_breakout_20d(self):
        # 25 closes, last close higher than all prior 20
        closes = [100.0 + i for i in range(25)]
        setups = mod.check_daily_setups(closes)
        self.assertIn("breakout_20d", setups)

    def test_daily_setups_oversold_and_bounce(self):
        # Plummeting closes: RSI < 30
        down_closes = [200.0 - (i * 5.0) for i in range(25)]
        setups = mod.check_daily_setups(down_closes)
        self.assertIn("oversold", setups)

        # Bounce: drop then last close ticks up
        bounce_closes = [200.0 - (i * 5.0) for i in range(24)] + [95.0]
        setups_bounce = mod.check_daily_setups(bounce_closes)
        self.assertIn("oversold_bounce", setups_bounce)

    def test_orb_setup_detection(self):
        # 7 bars: first 3 bars (09:15, 09:20, 09:25) establish OR high = 2510.0
        # Bar 6 closes at 2518.0 -> triggers ORB
        bars = [
            {"ist_time": "09:15", "high": 2505.0, "low": 2490.0, "close": 2500.0, "volume": 50000},
            {"ist_time": "09:20", "high": 2510.0, "low": 2485.0, "close": 2495.0, "volume": 40000},
            {"ist_time": "09:25", "high": 2508.0, "low": 2492.0, "close": 2505.0, "volume": 45000},
            {"ist_time": "09:30", "high": 2509.0, "low": 2502.0, "close": 2506.0, "volume": 35000},
            {"ist_time": "09:35", "high": 2508.0, "low": 2503.0, "close": 2507.0, "volume": 32000},
            {"ist_time": "09:40", "high": 2511.0, "low": 2505.0, "close": 2509.0, "volume": 38000},
            {"ist_time": "09:45", "high": 2520.0, "low": 2508.0, "close": 2518.0, "volume": 90000},
        ]
        res = mod.check_orb_setup(bars, or_minutes=15)
        self.assertIsNotNone(res)
        self.assertEqual(res["or_high"], 2510.0)
        self.assertEqual(res["or_low"], 2485.0)
        self.assertEqual(res["trigger_time"], "09:45")
        self.assertEqual(res["trigger_price"], 2518.0)
        self.assertGreater(res["pct_over"], 0.0)

    def test_orb_range_width_filter(self):
        # Range high 2510, low 2485 -> width = 1.01%
        bars = [
            {"ist_time": "09:15", "high": 2510.0, "low": 2485.0, "close": 2500.0, "volume": 50000},
            {"ist_time": "09:20", "high": 2505.0, "low": 2490.0, "close": 2495.0, "volume": 40000},
            {"ist_time": "09:25", "high": 2508.0, "low": 2492.0, "close": 2505.0, "volume": 45000},
            {"ist_time": "09:30", "high": 2520.0, "low": 2505.0, "close": 2518.0, "volume": 90000},
        ]
        # Normal width passes
        self.assertIsNotNone(mod.check_orb_setup(bars, or_minutes=15, min_or_width=0.4, max_or_width=2.0))

        # Too narrow (min_or_width = 1.5% > 1.01%) -> filtered out (None)
        self.assertIsNone(mod.check_orb_setup(bars, or_minutes=15, min_or_width=1.5, max_or_width=2.0))

        # Too wide (max_or_width = 0.5% < 1.01%) -> filtered out (None)
        self.assertIsNone(mod.check_orb_setup(bars, or_minutes=15, min_or_width=0.2, max_or_width=0.5))

    def test_orb_short_breakdown(self):
        # Range low is 2485.0. Bar 3 closes at 2475.0 (below range low)
        short_bars = [
            {"ist_time": "09:15", "high": 2510.0, "low": 2485.0, "close": 2500.0, "volume": 50000},
            {"ist_time": "09:20", "high": 2505.0, "low": 2490.0, "close": 2495.0, "volume": 40000},
            {"ist_time": "09:25", "high": 2508.0, "low": 2492.0, "close": 2505.0, "volume": 45000},
            {"ist_time": "09:30", "high": 2482.0, "low": 2470.0, "close": 2475.0, "volume": 90000},
        ]
        res = mod.check_orb_setup(short_bars, or_minutes=15, direction="short")
        self.assertIsNotNone(res)
        self.assertEqual(res["side"], "sell")
        self.assertEqual(res["trigger_price"], 2475.0)

    def test_cli_universe_offline(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out_file = os.path.join(tmpdir, "universe.txt")
            fix_csv = os.path.join(FIX, "trader-scanner", "EQUITY_L.csv")
            rc = mod.main(["universe", "--out", out_file, "--offline", fix_csv])
            self.assertEqual(rc, 0)
            self.assertTrue(os.path.isfile(out_file))
            with open(out_file) as f:
                content = f.read()
            self.assertIn("RELIANCE", content)
            self.assertIn("TCS", content)

    def test_cli_orb_offline(self):
        fix_dir = os.path.join(FIX, "trader-scanner")
        rc = mod.main([
            "orb", "--symbols", "RELIANCE", "--offline", fix_dir,
            "--now", "2026-10-19 10:15", "--no-write", "--json"
        ])
        self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()
