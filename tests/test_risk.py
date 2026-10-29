import datetime
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _load import load

mod = load("trader-risk", "check")


class TestRisk(unittest.TestCase):
    def setUp(self):
        self.cfg = {
            "budget_inr": 100000.0,
            "max_loss_per_trade_inr": 1000.0,
            "max_daily_loss_inr": 3000.0,
            "max_order_inr": 100000.0,
            "min_order_inr": 500.0,
            "max_position_pct": 50.0,
            "min_reward_risk": 1.0,
            "require_stop": True,
            "no_entries_before": "09:30",
            "no_entries_after": "10:15",
            "blocked": ["BLOCKEDSTOCK"],
        }
        self.valid_order = {
            "symbol": "RELIANCE",
            "side": "buy",
            "qty": 40,
            "entry_price": 2500.0,
            "stop_loss_price": 2480.0,  # Risk = 20 * 40 = 800 <= 1000
            "take_profit_price": 2540.0, # Reward = 40 * 40 = 1600 (R:R 2.0 >= 1.0)
            "order_type": "limit",
        }
        # Monday 10:15 IST (valid session)
        self.now_ist = datetime.datetime(2026, 10, 19, 10, 15, 0)

    def test_valid_order_passes(self):
        status, reasons = mod.check_order(
            self.valid_order, self.cfg, portfolio={}, broker_state={}, prices={}, now_ist=self.now_ist
        )
        self.assertEqual(status, "PASS")
        self.assertEqual(reasons, [])

    def test_block_missing_stop(self):
        bad_order = dict(self.valid_order)
        bad_order["stop_loss_price"] = 0.0
        status, reasons = mod.check_order(
            bad_order, self.cfg, portfolio={}, broker_state={}, prices={}, now_ist=self.now_ist
        )
        self.assertEqual(status, "BLOCK")
        self.assertTrue(any("stop-loss is required" in r for r in reasons))

    def test_block_stop_above_entry(self):
        bad_order = dict(self.valid_order)
        bad_order["stop_loss_price"] = 2510.0  # Above entry 2500
        status, reasons = mod.check_order(
            bad_order, self.cfg, portfolio={}, broker_state={}, prices={}, now_ist=self.now_ist
        )
        self.assertEqual(status, "BLOCK")
        self.assertTrue(any("stop-loss" in r and "above" in r for r in reasons))

    def test_block_exceeding_max_loss(self):
        bad_order = dict(self.valid_order)
        bad_order["qty"] = 100  # Risk = 20 * 100 = 2000 > 1000 limit
        status, reasons = mod.check_order(
            bad_order, self.cfg, portfolio={}, broker_state={}, prices={}, now_ist=self.now_ist
        )
        self.assertEqual(status, "BLOCK")
        self.assertTrue(any("max loss" in r for r in reasons))

    def test_block_poor_reward_risk(self):
        bad_order = dict(self.valid_order)
        bad_order["take_profit_price"] = 2510.0  # Reward = 10, Risk = 20 -> R:R 0.5 < 1.0
        status, reasons = mod.check_order(
            bad_order, self.cfg, portfolio={}, broker_state={}, prices={}, now_ist=self.now_ist
        )
        self.assertEqual(status, "BLOCK")
        self.assertTrue(any("reward:risk" in r for r in reasons))

    def test_block_blocked_ticker(self):
        bad_order = dict(self.valid_order)
        bad_order["symbol"] = "BLOCKEDSTOCK"
        status, reasons = mod.check_order(
            bad_order, self.cfg, portfolio={}, broker_state={}, prices={}, now_ist=self.now_ist
        )
        self.assertEqual(status, "BLOCK")
        self.assertTrue(any("blocked list" in r for r in reasons))

    def test_block_outside_trading_window(self):
        # 14:55 IST is after 14:45 cutoff
        late_ist = datetime.datetime(2026, 10, 19, 14, 55, 0)
        status, reasons = mod.check_order(
            self.valid_order, self.cfg, portfolio={}, broker_state={}, prices={}, now_ist=late_ist
        )
        self.assertEqual(status, "BLOCK")
        self.assertTrue(any("after entry window" in r for r in reasons))

    def test_block_weekend_and_holiday(self):
        # Sunday
        weekend_ist = datetime.datetime(2026, 10, 18, 10, 15, 0)
        status_wk, reasons_wk = mod.check_order(
            self.valid_order, self.cfg, portfolio={}, broker_state={}, prices={}, now_ist=weekend_ist
        )
        self.assertEqual(status_wk, "BLOCK")
        self.assertTrue(any("weekends" in r for r in reasons_wk))

        # Republic Day Holiday (2026-01-26)
        holiday_ist = datetime.datetime(2026, 1, 26, 10, 15, 0)
        status_hol, reasons_hol = mod.check_order(
            self.valid_order, self.cfg, portfolio={}, broker_state={}, prices={}, now_ist=holiday_ist
        )
        self.assertEqual(status_hol, "BLOCK")
        self.assertTrue(any("closed today" in r for r in reasons_hol))

    def test_nifty_market_regime_filter(self):
        cfg_with_nifty = dict(self.cfg)
        cfg_with_nifty["nifty_filter"] = True

        # Market down -1.5% (below -1.0% threshold)
        bear_prices = {
            "^NSEI": {"price": 24000.0, "prev_close": 24365.48, "change_pct": -1.5}
        }
        status, reasons = mod.check_order(
            self.valid_order, cfg_with_nifty, portfolio={}, broker_state={}, prices=bear_prices, now_ist=self.now_ist
        )
        self.assertEqual(status, "BLOCK")
        self.assertTrue(any("broad market risk" in r and "Nifty 50" in r for r in reasons))

        # Bullish or flat market (-0.2%) passes
        bull_prices = {
            "^NSEI": {"price": 24316.0, "prev_close": 24365.48, "change_pct": -0.2}
        }
        status_pass, reasons_pass = mod.check_order(
            self.valid_order, cfg_with_nifty, portfolio={}, broker_state={}, prices=bull_prices, now_ist=self.now_ist
        )
        self.assertEqual(status_pass, "PASS")
        self.assertEqual(reasons_pass, [])

    def test_valid_short_order_and_nifty_filter(self):
        short_order = {
            "symbol": "RELIANCE",
            "side": "sell",
            "qty": 20,
            "entry_price": 2500.0,
            "stop_loss_price": 2520.0,
            "take_profit_price": 2460.0,
            "order_type": "limit",
        }
        # Valid short order passes
        status, reasons = mod.check_order(
            short_order, self.cfg, portfolio={}, broker_state={}, prices={}, now_ist=self.now_ist
        )
        self.assertEqual(status, "PASS")
        self.assertEqual(reasons, [])

        # Short order with stop below entry should BLOCK
        bad_short = dict(short_order)
        bad_short["stop_loss_price"] = 2480.0
        bad_status, bad_reasons = mod.check_order(
            bad_short, self.cfg, portfolio={}, broker_state={}, prices={}, now_ist=self.now_ist
        )
        self.assertEqual(bad_status, "BLOCK")
        self.assertTrue(any("below entry price" in r for r in bad_reasons))


if __name__ == "__main__":
    unittest.main()
