import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _load import load

mod = load("trader-budget", "size")


class TestBudget(unittest.TestCase):
    def test_indian_charges_calculation(self):
        # Buy 100 shares @ 2500, Sell @ 2550
        # Buy turnover = 2,50,000, Sell turnover = 2,55,000, Total = 5,05,000
        charges = mod.calculate_indian_charges(buy_price=2500.0, sell_price=2550.0, qty=100, is_intraday=True)

        # STT: 0.025% on 2,55,000 = 63.75
        self.assertEqual(charges["stt"], 63.75)

        # NSE charges: 0.00297% on 5,05,000 = 15.00
        self.assertAlmostEqual(charges["nse_charges"], 15.00, places=1)

        # SEBI fee: 0.0001% on 5,05,000 = 0.51
        self.assertAlmostEqual(charges["sebi_fee"], 0.51, places=1)

        # Stamp duty: 0.003% on 2,50,000 = 7.50
        self.assertEqual(charges["stamp_duty"], 7.50)

        # Brokerage: capped at 20 + 20 = 40.00
        self.assertEqual(charges["brokerage"], 40.00)

        # GST: 18% on (40.00 + 15.00 + 0.51) = 9.99
        self.assertAlmostEqual(charges["gst"], 9.99, places=1)

        # Total charges should be around ~136.75
        self.assertGreater(charges["total_charges"], 130.0)
        self.assertLess(charges["total_charges"], 145.0)

        # Breakeven per share = total_charges / 100 ~ 1.37
        self.assertGreater(charges["breakeven_per_share"], 1.20)
        self.assertLess(charges["breakeven_per_share"], 1.50)

    def test_shares_calculation_risk_budget(self):
        # Entry: 2518.00, Stop: 2495.00 -> Risk = 23.00
        # Max loss = 1000.00 INR
        # Expected shares: floor(1000 / 23) = 43 shares
        cfg = {
            "budget_inr": 100000.0,
            "max_loss_per_trade_inr": 1000.0,
            "max_order_inr": 200000.0,
            "max_position_pct": 75.0,
            "cash_buffer_pct": 10.0,
            "intraday_leverage": 5.0,
        }
        res = mod.calculate_shares(entry_price=2518.00, stop_price=2495.00, config=cfg)
        self.assertEqual(res["shares"], 43)

    def test_size_trade_bracket_order(self):
        plan = {
            "symbol": "RELIANCE",
            "entry_price": 2518.00,
            "stop_price": 2495.00,
            "target_price": 2564.00,
        }
        cfg = {
            "budget_inr": 100000.0,
            "max_loss_per_trade_inr": 1000.0,
            "intraday_leverage": 5.0,
        }
        order = mod.size_trade(plan, cfg)
        self.assertEqual(order["symbol"], "RELIANCE")
        self.assertEqual(order["exchange"], "NSE")
        self.assertEqual(order["product"], "MIS")
        self.assertEqual(order["qty"], 43)
        self.assertLessEqual(order["max_loss_inr"], 1000.0)
        self.assertGreater(order["gross_reward_inr"], 0)
        self.assertIn("statutory_charges_target_inr", order)
        self.assertIn("net_profit_target_inr", order)

    def test_refuse_when_risk_exceeds_budget(self):
        # Entry 2500, Stop 2000 -> Risk = 500 per share
        # Max loss 100 -> 0 shares
        cfg = {"budget_inr": 10000.0, "max_loss_per_trade_inr": 100.0}
        with self.assertRaises(mod.SizeError):
            mod.calculate_shares(entry_price=2500.00, stop_price=2000.00, config=cfg)


if __name__ == "__main__":
    unittest.main()
