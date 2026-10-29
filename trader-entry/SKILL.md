---
name: trader-entry
description: >-
  Entry Timer for Indian Equities (NSE & BSE). Watches intraday 5-minute or 1-minute
  candlestick charts bar by bar for breakout triggers above the 15-minute Opening Range
  (09:15-09:30 AM IST) or breakdown triggers below the range. Validates confirmed candle closes,
  evaluates relative volume expansion, and strictly respects Indian market session windows
  (09:30 to 10:15 IST prime time), preventing late entries before broker intraday auto-square-off (15:15 IST).
  Supports both Long breakouts and Short breakdowns. Writes trader/entry.json upon trigger.
argument-hint: "[check | watch | watchlist] TICKER [--setup orb|level] [--direction long|short|both]"
---

# trader-entry

The Entry Timer watches setups bar by bar and triggers on confirmed candle closes.
It does not guess or predict: a wick through a level is ignored; only a closed candle
above the range high (Long) or below the range low (Short) triggers the entry. Supports bi-directional trading.

This tool is not financial advice. No order is ever placed automatically. You must
explicitly say yes to any trade.

`${CLAUDE_SKILL_DIR}` below is this skill's folder.

```bash
python3 "${CLAUDE_SKILL_DIR}/entry.py" check RELIANCE                       # check 15-min ORB long breakout
python3 "${CLAUDE_SKILL_DIR}/entry.py" check RELIANCE --direction short     # check 15-min ORB short breakdown
python3 "${CLAUDE_SKILL_DIR}/entry.py" check RELIANCE --direction both      # check either long or short
python3 "${CLAUDE_SKILL_DIR}/entry.py" check TCS --setup level --level 3750  # check resistance breakout
python3 "${CLAUDE_SKILL_DIR}/entry.py" check INFY --rvol-mult 1.25 --write  # volume surge confirmation
python3 "${CLAUDE_SKILL_DIR}/entry.py" watch RELIANCE --every 30 --until 10:15 # bar by bar monitor
python3 "${CLAUDE_SKILL_DIR}/entry.py" watchlist                             # check all scanner hits
```

Flags: `--setup orb` (default) or `level`, `--direction long` (default), `short`, `both`,
`--level PRICE`, `--or-minutes 15`, `--min-volume-x 1.0`, `--rvol-mult 1.0`,
`--min-or-width 0.4`, `--max-or-width 2.0`, `--min-close-pos 0.65`, `--max-upper-wick 0.35`,
`--until 10:15` (Prime Time Window), `--require-vwap` (default enabled), `--no-vwap`,
`--interval 5m`, `--now "YYYY-MM-DD HH:MM IST"`, `--offline FILE`, `--write`.

## Accuracy Improvements
- **Bi-directional Capability (Long & Short)**: Captures breakouts on bullish days and breakdowns on market selloff days, turning bear markets into winning sessions.
- **Prime Time Window (09:30 - 10:15 IST)**: Enforces entry execution during the morning institutional order flow, blocking midday chop traps.
- **Wick Rejection Filter**: Rejects long breakouts with > 35% upper wicks (seller rejection) and short breakdowns with > 35% lower wicks (buyer rejection).
- **Intraday VWAP Filter**: Blocks long triggers below VWAP and short triggers above VWAP.
- **Range Width Filter**: Only trades ranges between 0.4% and 2.0% width (avoids illiquid chops < 0.4% and exhausted ranges > 2.0%).
- **Rolling RVol Surge**: Evaluates breakout bar volume against the preceding 5-bar rolling average.

## What it reads and writes

| file | what |
| --- | --- |
| `trader/watchlist.json` | read by `watchlist`: candidates to check |
| `trader/config.json` | read: `no_entries_before` (09:30), `no_entries_after` (10:15), filter rules |
| `trader/entry.json` | written when triggered: contains `symbol`, `side` (buy/sell), `direction`, `entry_price`, `trigger_time`, `or_high`, `or_low`, `or_width_pct`, `close_pos_pct`, `upper_wick_pct`, `vwap`, `rvol` |

## Statuses
- `triggered`: A candle has completed and closed above the range high (long) or below range low (short).
- `waiting`: Range is still forming or price is trading within the range.
- `expired`: Time passed `no_entries_after` (10:15 IST) without a breakout.
- `no-data`: Market closed, weekend, or holiday.
