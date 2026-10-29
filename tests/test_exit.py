import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _load import load

mod = load("trader-exit", "exit")


class TestExit(unittest.TestCase):
    def test_or_mid_stop_and_2r_target(self):
        # Entry: 2518.00, or_high: 2510.00, or_low: 2480.00
        # or_mid = (2510 + 2480)/2 = 2495.00
        # Risk = 2518 - 2495 = 23.00
        # Target 2R = 2518 + 2 * 23.00 = 2564.00
        plan = mod.build_plan(
            symbol="RELIANCE",
            entry_price=2518.00,
            or_high=2510.00,
            or_low=2480.00,
            stop_rule="or-mid",
            target_rule="2R",
            flat_by="15:15",
        )
        self.assertEqual(plan["symbol"], "RELIANCE")
        self.assertEqual(plan["entry_price"], 2518.00)
        self.assertEqual(plan["stop_price"], 2495.00)
        self.assertEqual(plan["target_price"], 2564.00)
        self.assertEqual(plan["risk_per_share"], 23.00)
        self.assertEqual(plan["reward_per_share"], 46.00)
        self.assertEqual(plan["reward_risk_ratio"], 2.0)
        self.assertEqual(plan["flat_by"], "15:15")

    def test_or_low_stop_and_1r_target(self):
        plan = mod.build_plan(
            symbol="TCS",
            entry_price=3800.00,
            or_high=3790.00,
            or_low=3760.00,
            stop_rule="or-low",
            target_rule="1R",
        )
        self.assertEqual(plan["stop_price"], 3760.00)
        self.assertEqual(plan["risk_per_share"], 40.00)
        self.assertEqual(plan["target_price"], 3840.00)
        self.assertEqual(plan["reward_risk_ratio"], 1.0)

    def test_pct_stop_calculation(self):
        # 1% stop on 1000.00 -> 990.00
        plan = mod.build_plan(
            symbol="INFY",
            entry_price=1000.00,
            stop_rule="pct:1",
            target_rule="1.5R",
        )
        self.assertEqual(plan["stop_price"], 990.00)
        self.assertEqual(plan["risk_per_share"], 10.00)
        self.assertEqual(plan["target_price"], 1015.00)

    def test_nse_tick_rounding_005(self):
        # Should round to nearest ₹0.05
        rounded = mod.round_tick(2518.03)
        self.assertEqual(float(rounded), 2518.00)
        rounded_up = mod.round_tick(2518.04, mod.ROUND_HALF_UP)
        self.assertEqual(float(rounded_up), 2518.05)

    def test_refuse_invalid_stop(self):
        with self.assertRaises(mod.PlanError):
            mod.build_plan("RELIANCE", entry_price=2500.00, stop_rule="price:2510.00")

    def test_refuse_tight_risk_under_threshold(self):
        # 0.05% of 2500 is 1.25. Risk of 0.50 should be refused as inside noise
        with self.assertRaises(mod.PlanError):
            mod.build_plan("RELIANCE", entry_price=2500.00, stop_rule="price:2499.50")

    def test_cli_plan(self):
        rc = mod.main([
            "plan", "--symbol", "RELIANCE", "--entry", "2518.00",
            "--or-high", "2510.00", "--or-low", "2480.00",
            "--stop", "or-mid", "--target", "2R", "--no-write", "--json"
        ])
        self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()
