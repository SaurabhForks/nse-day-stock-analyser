---
name: trader-entry
description: >-
  Entry Timer for Indian Equities (NSE & BSE). Watches intraday 5-minute or 1-minute
  candlestick charts bar by bar for breakout triggers above the 15-minute Opening Range
  (09:15-09:30 AM IST) or custom breakout levels. Validates confirmed candle closes,
  evaluates relative volume expansion, and strictly respects Indian market session windows
  (09:30 to 14:45 IST), preventing late entries before broker intraday auto-square-off (15:15 IST).
  Writes trader/entry.json upon breakout trigger. Use when the user asks to time an entry,
  watch a breakout candle on an Indian stock, or check if an NSE setup has triggered.
argument-hint: "[check | watch | watchlist] TICKER [--setup orb|level]"
---

# trader-entry

The Entry Timer watches setups bar by bar and triggers on confirmed candle closes.
It does not guess or predict: a wick through a level is ignored; only a closed candle
above the range high or resistance level triggers the entry. Long side only.

This tool is not financial advice. No order is ever placed automatically. You must
explicitly say yes to any trade.

`${CLAUDE_SKILL_DIR}` below is this skill's folder.

```bash
python3 "${CLAUDE_SKILL_DIR}/entry.py" check RELIANCE                       # check 15-min ORB trigger
python3 "${CLAUDE_SKILL_DIR}/entry.py" check TCS --setup level --level 3750  # check resistance breakout
python3 "${CLAUDE_SKILL_DIR}/entry.py" check INFY --min-volume-x 1.2 --write # volume confirmation
python3 "${CLAUDE_SKILL_DIR}/entry.py" watch RELIANCE --every 30 --until 14:45 # bar by bar monitor
python3 "${CLAUDE_SKILL_DIR}/entry.py" watchlist                             # check all scanner hits
```

Flags: `--setup orb` (default) or `level`, `--level PRICE`, `--or-minutes 15`,
`--min-volume-x 1.0`, `--rvol-mult 1.0`, `--min-or-width 0.4`, `--max-or-width 2.0`,
`--require-vwap` (default enabled), `--no-vwap`, `--interval 5m`,
`--now "YYYY-MM-DD HH:MM IST"`, `--offline FILE`, `--write`.

## Accuracy Improvements
- **Intraday VWAP Filter**: Blocks ORB long triggers if the candle closes below the cumulative session VWAP.
- **Range Width Filter**: Only trades ranges between 0.4% and 2.0% width (avoids illiquid chops < 0.4% and exhausted ranges > 2.0%).
- **Rolling RVol Surge**: Evaluates breakout bar volume against the preceding 5-bar rolling average.

## What it reads and writes

| file | what |
| --- | --- |
| `trader/watchlist.json` | read by `watchlist`: candidates to check |
| `trader/config.json` | read: `no_entries_before` (09:30), `no_entries_after` (14:45), filter rules |
| `trader/entry.json` | written when triggered: contains `symbol`, `entry_price`, `trigger_time`, `or_high`, `or_low`, `or_width_pct`, `vwap`, `rvol` |

## Statuses
- `triggered`: A candle has completed and closed above the range high / level.
- `waiting`: Range is still forming or price is trading within the range.
- `expired`: Time passed `no_entries_after` (14:45 IST) without a breakout.
- `no-data`: Market closed, weekend, or holiday.
