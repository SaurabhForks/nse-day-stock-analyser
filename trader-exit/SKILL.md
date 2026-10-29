---
name: trader-exit
description: >-
  Exit Planner for Indian Equities (NSE & BSE). Calculates objective stop-loss and
  profit targets before entering an intraday position, enforcing risk discipline.
  Supports opening-range midpoint (or-mid), opening range low (or-low), percentage,
  fixed price, and ATR-based stops, along with 1R, 1.5R, 2R, and 3R risk-multiple targets.
  Supports both Long (buy) and Short (sell) trades.
  Rounds prices to the NSE tick size (₹0.05) and enforces mandatory MIS intraday
  flattening at 15:15 IST before Indian brokers execute auto-square-off penalties.
  Writes trader/plan.json. Use when the user asks where to set a stop loss, target,
  or calculate risk-reward on an Indian stock trade.
argument-hint: "[plan | show] [--side buy|sell] [--stop or-mid|or-low|pct:X|price:X] [--target 1R|2R]"
---

# trader-exit

The Exit Planner sets your stop-loss and profit target before you enter a trade.
Knowing when to exit protects your capital from emotional decision-making. Supports both Longs and Shorts.

This tool is not financial advice. No order is ever placed automatically. You must
explicitly say yes to any trade.

`${CLAUDE_SKILL_DIR}` below is this skill's folder.

```bash
python3 "${CLAUDE_SKILL_DIR}/exit.py" plan                                    # from trader/entry.json: or-mid stop, 2R target
python3 "${CLAUDE_SKILL_DIR}/exit.py" plan --side sell                        # short sell plan
python3 "${CLAUDE_SKILL_DIR}/exit.py" plan --stop or-mid --target 1R --write  # 1R target with midpoint stop
python3 "${CLAUDE_SKILL_DIR}/exit.py" plan --symbol RELIANCE --entry 2500 --or-high 2490 --or-low 2470
python3 "${CLAUDE_SKILL_DIR}/exit.py" plan --symbol TCS --entry 3800 --stop pct:1 --target 2R
python3 "${CLAUDE_SKILL_DIR}/exit.py" show                                    # view current plan
```

Flags: `--side buy` (default) or `sell`, `--stop or-mid` (default for ORB), `or-low`, `price:X`, `pct:X`, `atr:K`;
`--target 2R` (default), `1R`, `1.5R`, `3R`, `price:X`; `--write`, `--json`.

## What it reads and writes

| file | what |
| --- | --- |
| `trader/entry.json` | read: entry price, side (buy/sell), OR high, OR low from entry timer |
| `trader/config.json` | read: `flat_by` (default 15:15 IST) |
| `trader/plan.json` | written: full exit plan with entry, stop, target, R:R ratio, flat_by, `breakeven_trigger_price` (1.2R), and `breakeven_stop_price` (entry ± ₹0.10) |

## Breakeven Trailing Rule (+1.2R Rule)
Every plan automatically calculates:
- `breakeven_trigger_price`: Trigger price when the trade reaches 1.2R in profit (+1.2R for long, -1.2R for short).
- `breakeven_stop_price`: Trailing stop adjusted to `entry + ₹0.10` (long) or `entry - ₹0.10` (short) to eliminate downside risk and cover slippage/charges once the breakout retest zone is cleared.

## Stop Rules
- `or-mid`: Midpoint of the 15-minute opening range `(high + low) / 2`
- `or-low`: Low of the 15-minute opening range (protective stop for long)
- `or-high`: High of the 15-minute opening range (protective stop for short)
- `pct:X`: X percent below entry price (long) or above entry price (short)
- `atr:K`: K times 14-period Average True Range away from entry
- `price:X`: Explicit rupee stop price
