import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _load import load, FIX

mod = load("trader-timemachine", "timemachine")


class TestTimeMachine(unittest.TestCase):
    def test_group_sessions(self):
        fix_gz = os.path.join(FIX, "trader-timemachine", "RELIANCE-60d5m.json.gz")
        chart = mod.fetch_60d_bars("RELIANCE", offline=fix_gz)
        sessions = mod.group_sessions(chart)
        self.assertGreaterEqual(len(sessions), 20)
        # Verify 75 bars per session (Indian market session)
        first_d = list(sessions.keys())[0]
        self.assertEqual(len(sessions[first_d]), 75)

    def test_ratio_pool_builder(self):
        fix_gz = os.path.join(FIX, "trader-timemachine", "RELIANCE-60d5m.json.gz")
        chart = mod.fetch_60d_bars("RELIANCE", offline=fix_gz)
        sessions = mod.group_sessions(chart)
        pool = mod.build_ratio_pool(sessions)
        self.assertIn(1, pool)
        self.assertIn(74, pool)
        self.assertGreater(len(pool[1]), 0)

    def test_monte_carlo_stable_seed(self):
        # Create artificial ratio pool: 1.002 on avg
        pool = {i: [(1.0, 1.005, 0.995, 1.001)] for i in range(75)}
        res1 = mod.run_monte_carlo(
            entry_price=2500.0,
            stop_price=2480.0,
            target_price=2540.0,
            start_slot=6,
            end_slot=72,
            ratio_pool=pool,
            replays=1000,
            seed=19,
        )
        res2 = mod.run_monte_carlo(
            entry_price=2500.0,
            stop_price=2480.0,
            target_price=2540.0,
            start_slot=6,
            end_slot=72,
            ratio_pool=pool,
            replays=1000,
            seed=19,
        )
        self.assertEqual(res1["target_pct"], res2["target_pct"])
        self.assertEqual(res1["stop_pct"], res2["stop_pct"])
        self.assertIn("verdict", res1)

    def test_historical_backtest_replay(self):
        fix_gz = os.path.join(FIX, "trader-timemachine", "RELIANCE-60d5m.json.gz")
        chart = mod.fetch_60d_bars("RELIANCE", offline=fix_gz)
        sessions = mod.group_sessions(chart)
        hist = mod.replay_historical_setup(sessions, or_minutes=15, target_r=2.0)
        self.assertIn("historical_sessions", hist)
        self.assertIn("win_rate", hist)

    def test_cli_timemachine_run_offline(self):
        fix_gz = os.path.join(FIX, "trader-timemachine", "RELIANCE-60d5m.json.gz")
        rc = mod.main([
            "run", "--symbol", "RELIANCE", "--entry", "2518.0",
            "--stop", "2495.0", "--target", "2564.0", "--entry-time", "09:45",
            "--until", "15:15", "--replays", "1000", "--seed", "19",
            "--offline", fix_gz, "--json"
        ])
        self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()
