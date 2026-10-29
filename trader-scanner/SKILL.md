---
name: trader-scanner
description: >-
  Chart Scanner for Indian Stock Market (NSE & BSE). Scans thousands of NSE equity
  charts for high-probability day trading setups: 15-minute / 30-minute Opening Range
  Breakouts (ORB) starting at 09:15 AM IST, 20-day high breakouts, bull flags,
  oversold bounces, and 20 EMA reclaims. Builds universe of NSE common equity shares,
  runs pre-market and intraday scans using free Yahoo Finance chart data, and writes
  trader/watchlist.json for trader-news and trader-entry. Use when the user asks to
  scan Indian stocks, find NSE breakout setups, look for Nifty momentum stocks, or
  prepare the morning watchlist before the market opens.
argument-hint: "[universe | daily | orb] [--at HH:MM]"
---

# trader-scanner

The Chart Scanner is the first step of an Indian market day trade. It scans thousands
of free NSE and BSE charts and filters the ones matching defined technical rules.
A scan is a list of charts matching a rule, not a recommendation to buy.
Most people who day trade lose money; the scanner only eliminates manual chart flipping.

This tool is not financial advice. No order is ever placed automatically. You must
explicitly say yes to any trade.

`${CLAUDE_SKILL_DIR}` below is this skill's folder.

```bash
python3 "${CLAUDE_SKILL_DIR}/scan.py" universe                       # -> trader/universe.txt
python3 "${CLAUDE_SKILL_DIR}/scan.py" daily                          # before 09:15 AM IST -> trader/watchlist.json
python3 "${CLAUDE_SKILL_DIR}/scan.py" daily --symbols RELIANCE,TCS   # scan specific Indian stocks
python3 "${CLAUDE_SKILL_DIR}/scan.py" orb                            # after 09:30 AM IST -> trader/watchlist.json
python3 "${CLAUDE_SKILL_DIR}/scan.py" orb --at 10:15                 # evaluate breakouts up to 10:15 AM IST
python3 "${CLAUDE_SKILL_DIR}/scan.py" orb --watchlist trader/watchlist.json --json
```

Flags: `--min-price 10` (INR), `--min-volume 100000`, `--or-minutes 15` (default 15 minutes: 09:15 to 09:30 IST),
`--min-or-width 0.4` (minimum OR width %, default 0.4%), `--max-or-width 2.0` (maximum OR width %, default 2.0%),
`--now "2026-10-19 10:15"` (IST time) to pin the clock, `--offline PATH`, `--no-write`, `--json`.

## What it reads and writes

| file | what |
| --- | --- |
| `trader/universe.txt` | written by `universe`: one `SYMBOL\|Name` per line |
| `trader/watchlist.json` | written by `daily` and `orb`: contains `hits[]` read by trader-news and trader-entry |
| `trader/config.json` | read by `orb`: `no_entries_after` (default 14:45 IST) |

## Indian Market Timing
- **Market Open**: 09:15 AM IST
- **Opening Range**: 09:15 to 09:30 AM IST (first three 5-minute candles: 09:15, 09:20, 09:25)
- **Intraday Square-off (MIS)**: 03:15 PM IST
- **Market Close**: 03:30 PM IST
- **Total Bars**: 75 five-minute bars per regular session
