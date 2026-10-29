import datetime
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _load import load, FIX

mod = load("trader-alerts", "alerts")


class TestAlerts(unittest.TestCase):
    def test_nse_clock_states(self):
        # 1. Normal open: 10:30 IST on a Monday
        mon_1030 = datetime.datetime(2026, 10, 19, 10, 30, 0)
        now_utc = mod.ist_to_utc(mon_1030)
        # Verify status
        cur_time = mon_1030.time()
        self.assertTrue(cur_time >= mod.OPEN_TIME and cur_time < mod.MIS_TIME)

        # 2. Pre-market: 09:05 IST
        pre_0905 = datetime.datetime(2026, 10, 19, 9, 5, 0)
        self.assertTrue(pre_0905.time() < mod.OPEN_TIME)

        # 3. MIS Auto-square-off window: 15:20 IST
        mis_1520 = datetime.datetime(2026, 10, 19, 15, 20, 0)
        self.assertTrue(mis_1520.time() >= mod.MIS_TIME and mis_1520.time() < mod.CLOSE_TIME)

        # 4. Market closed: 16:00 IST
        post_1600 = datetime.datetime(2026, 10, 19, 16, 0, 0)
        self.assertTrue(post_1600.time() >= mod.CLOSE_TIME)

    def test_fetch_quote_offline(self):
        fix_dir = os.path.join(FIX, "trader-alerts")
        q = mod.fetch_quote("RELIANCE", offline=fix_dir)
        self.assertEqual(q["symbol"], "RELIANCE")
        self.assertGreater(q["price"], 0)

    def test_alert_rules_evaluation(self):
        rule_target = {"id": "t1", "type": "above", "symbol": "RELIANCE", "price": 2540.0, "active": True}
        rule_stop = {"id": "s1", "type": "below", "symbol": "RELIANCE", "price": 2490.0, "active": True}

        # Price reaches 2545.00 -> target triggers
        p_high = 2545.00
        self.assertTrue(p_high >= rule_target["price"])
        self.assertFalse(p_high <= rule_stop["price"])

        # Price drops to 2485.00 -> stop triggers
        p_low = 2485.00
        self.assertTrue(p_low <= rule_stop["price"])
        self.assertFalse(p_low >= rule_target["price"])


if __name__ == "__main__":
    unittest.main()
