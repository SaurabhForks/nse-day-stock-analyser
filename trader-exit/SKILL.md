---
name: trader-exit
description: >-
  Exit Planner for Indian Equities (NSE & BSE). Calculates objective stop-loss and
  profit targets before entering an intraday position, enforcing risk discipline.
  Supports opening-range midpoint (or-mid), opening range low (or-low), percentage,
  fixed price, and ATR-based stops, along with 1R, 1.5R, 2R, and 3R risk-multiple targets.
  Rounds prices to the NSE tick size (₹0.05) and enforces mandatory MIS intraday
  flattening at 15:15 IST before Indian brokers execute auto-square-off penalties.
  Writes trader/plan.json. Use when the user asks where to set a stop loss, target,
  or calculate risk-reward on an Indian stock trade.
argument-hint: "[plan | show] [--stop or-mid|or-low|pct:X|price:X] [--target 1R|2R]"
---

# trader-exit

The Exit Planner sets your stop-loss and profit target before you enter a trade.
Knowing when to exit protects your capital from emotional decision-making. Longs only.

This tool is not financial advice. No order is ever placed automatically. You must
explicitly say yes to any trade.

`${CLAUDE_SKILL_DIR}` below is this skill's folder.

```bash
python3 "${CLAUDE_SKILL_DIR}/exit.py" plan                                    # from trader/entry.json: or-mid stop, 2R target
python3 "${CLAUDE_SKILL_DIR}/exit.py" plan --stop or-mid --target 1R --write  # 1R target with midpoint stop
python3 "${CLAUDE_SKILL_DIR}/exit.py" plan --symbol RELIANCE --entry 2500 --or-high 2490 --or-low 2470
python3 "${CLAUDE_SKILL_DIR}/exit.py" plan --symbol TCS --entry 3800 --stop pct:1 --target 2R
python3 "${CLAUDE_SKILL_DIR}/exit.py" show                                    # view current plan
```

Flags: `--stop or-mid` (default for ORB), `or-low`, `price:X`, `pct:X`, `atr:K`;
`--target 2R` (default), `1R`, `1.5R`, `3R`, `price:X`; `--write`, `--json`.

## What it reads and writes

| file | what |
| --- | --- |
| `trader/entry.json` | read: entry price, OR high, OR low from entry timer |
| `trader/config.json` | read: `flat_by` (default 15:15 IST) |
| `trader/plan.json` | written: full exit plan with entry, stop, target, R:R ratio, and flat_by |

## Stop Rules
- `or-mid`: Midpoint of the 15-minute opening range `(high + low) / 2`
- `or-low`: Low of the 15-minute opening range
- `pct:X`: X percent below entry price
- `atr:K`: K times 14-period Average True Range below entry
- `price:X`: Explicit rupee stop price
