import json
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _load import ROOT

SKILLS = [
    "trader-scanner", "trader-news", "trader-entry", "trader-exit", "trader-timemachine",
    "trader-risk", "trader-budget", "trader-broker", "trader-alerts", "trader-analyst",
    "trader-insider"
]
ABOUT = ("11 Claude skills for Indian stock market day trading: scan thousands of NSE/BSE charts, track corporate "
         "news, time every entry and exit, and replay every outcome before you risk a rupee.")

ORDER_PATH = [
    "trader-scanner", "trader-entry", "trader-exit", "trader-timemachine", "trader-budget",
    "trader-insider", "trader-risk", "trader-broker", "trader-alerts"
]


def frontmatter(path):
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    return (m.group(1) if m else ""), text


def every_text_file():
    for base, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in (".git", "__pycache__")]
        for f in files:
            if f.endswith((".md", ".py", ".json", ".csv", ".txt", ".xml")) or f == "LICENSE":
                yield os.path.join(base, f)


class Repo(unittest.TestCase):
    def test_eleven_skill_folders_at_the_root(self):
        found = sorted(d for d in os.listdir(ROOT)
                       if os.path.isfile(os.path.join(ROOT, d, "SKILL.md")))
        self.assertEqual(found, sorted(SKILLS))

    def test_root_structure(self):
        root = sorted(d for d in os.listdir(ROOT) if not d.startswith(".git"))
        expected = sorted([".claude-plugin", "LICENSE", "README.md", "tests"] + SKILLS)
        # Verify all expected components are in root
        for item in expected:
            self.assertIn(item, root)

    def test_frontmatter_name_and_description(self):
        for s in SKILLS:
            fm, text = frontmatter(os.path.join(ROOT, s, "SKILL.md"))
            self.assertIn("name: %s\n" % s, fm + "\n", s)
            self.assertRegex(fm, r"description: ", s)
            self.assertGreater(len(fm), 180, "%s description is too thin" % s)
            self.assertGreater(len(text.splitlines()), 35, s)

    def test_order_path_skills_carry_the_safety_rule(self):
        for s in ORDER_PATH:
            _, text = frontmatter(os.path.join(ROOT, s, "SKILL.md"))
            low = " ".join(text.lower().split())
            self.assertIn("not financial advice", low, s)
            self.assertIn("yes", low, s)

    def test_plugin_manifest_points_at_the_root_skills(self):
        with open(os.path.join(ROOT, ".claude-plugin", "plugin.json")) as fh:
            plugin = json.load(fh)
        self.assertEqual(plugin["name"], "indian-day-trader-skill")
        self.assertEqual(plugin["skills"], "./")
        with open(os.path.join(ROOT, ".claude-plugin", "marketplace.json")) as fh:
            market = json.load(fh)
        self.assertEqual(market["name"], "indian-day-trader-skill")
        self.assertEqual(market["plugins"][0]["name"], "indian-day-trader-skill")

    def test_every_tool_runs_on_python_3_8(self):
        for s in SKILLS:
            folder = os.path.join(ROOT, s)
            for f in os.listdir(folder):
                if not f.endswith(".py"):
                    continue
                with open(os.path.join(folder, f), encoding="utf-8") as fh:
                    src = fh.read()
                for bad in ("import zoneinfo", "from zoneinfo", ".removeprefix(", ".removesuffix(",
                            "list[", "dict[", "tuple["):
                    if bad.endswith("["):
                        self.assertNotRegex(src, r"(?<![\w.])%s" % re.escape(bad), "%s/%s" % (s, f))
                    else:
                        self.assertNotIn(bad, src, "%s/%s" % (s, f))

    def test_example_config_has_indian_parameters(self):
        with open(os.path.join(ROOT, "trader-budget", "config.example.json")) as fh:
            cfg = json.load(fh)
        for k in ("budget_inr", "max_loss_per_trade_inr", "max_daily_loss_inr", "max_trades_per_day",
                  "min_reward_risk", "require_stop", "no_entries_after", "flat_by", "intraday_leverage"):
            self.assertIn(k, cfg, k)
        self.assertIs(cfg["require_stop"], True)
        self.assertIs(cfg["paper"], True)
        self.assertEqual(cfg["flat_by"], "15:15")


if __name__ == "__main__":
    unittest.main()
