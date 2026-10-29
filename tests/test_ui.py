"""
Unit tests for Day Trader UI Server.
"""

import unittest
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _load import load

mod = load("trader-ui", "server")


class TestDayTraderUI(unittest.TestCase):

    def test_static_html_exists(self):
        index_file = os.path.join(mod.STATIC_DIR, "index.html")
        self.assertTrue(os.path.exists(index_file))

    def test_ist_now(self):
        ist = mod.get_ist_now()
        self.assertIsNotNone(ist)


if __name__ == "__main__":
    unittest.main()
