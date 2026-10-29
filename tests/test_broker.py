import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _load import load

mod = load("trader-broker", "ticket")


class TestBroker(unittest.TestCase):
    def test_format_zerodha_kite_payload(self):
        order = {
            "symbol": "RELIANCE",
            "side": "buy",
            "qty": 43,
            "order_type": "limit",
            "entry_price": 2518.00,
            "limit_price": 2518.00,
            "stop_loss_price": 2495.00,
            "take_profit_price": 2564.00,
        }
        payload = mod.format_zerodha_kite_payload(order)
        self.assertEqual(payload["tradingsymbol"], "RELIANCE")
        self.assertEqual(payload["exchange"], "NSE")
        self.assertEqual(payload["transaction_type"], "BUY")
        self.assertEqual(payload["quantity"], 43)
        self.assertEqual(payload["product"], "MIS")
        self.assertEqual(payload["order_type"], "LIMIT")
        self.assertEqual(payload["price"], 2518.00)
        self.assertEqual(payload["stoploss"], 23.00)   # 2518 - 2495
        self.assertEqual(payload["squareoff"], 46.00)  # 2564 - 2518

    def test_explicit_yes_validation(self):
        # Valid confirmations
        ok1, _ = mod.is_explicit_yes("yes RELIANCE", symbol="RELIANCE", qty=43)
        self.assertTrue(ok1)

        ok2, _ = mod.is_explicit_yes("yes 43", symbol="RELIANCE", qty=43)
        self.assertTrue(ok2)

        ok3, _ = mod.is_explicit_yes("yes", symbol="RELIANCE", qty=43)
        self.assertTrue(ok3)

        # Invalid: vague words
        bad1, _ = mod.is_explicit_yes("sure", symbol="RELIANCE")
        self.assertFalse(bad1)

        bad2, _ = mod.is_explicit_yes("ok", symbol="RELIANCE")
        self.assertFalse(bad2)

        # Invalid: batch approval
        bad_batch, _ = mod.is_explicit_yes("yes to all", symbol="RELIANCE")
        self.assertFalse(bad_batch)

        # Invalid: doubt / hesitation
        bad_doubt, _ = mod.is_explicit_yes("yes but wait", symbol="RELIANCE")
        self.assertFalse(bad_doubt)

        # Invalid: naming a different stock
        bad_sym, _ = mod.is_explicit_yes("yes TCS", symbol="RELIANCE")
        self.assertFalse(bad_sym)

    def test_order_fingerprint_deterministic(self):
        ord1 = {"symbol": "RELIANCE", "qty": 10, "entry_price": 2500.0}
        ord2 = {"qty": 10, "symbol": "RELIANCE", "entry_price": 2500.0}
        fp1 = mod.order_fingerprint(ord1)
        fp2 = mod.order_fingerprint(ord2)
        self.assertEqual(fp1, fp2)


if __name__ == "__main__":
    unittest.main()
