---
name: trader-risk
description: >-
  Pre-Trade Risk Manager for Indian Equities (NSE & BSE). Evaluates proposed bracket
  orders against strict risk boundaries, capital limits, and statutory trading hours.
  Enforces max loss per trade in rupees (₹), max daily drawdown, position caps,
  stop-loss requirements, reward-to-risk minimums, duplicate order detection, and
  NSE session trading windows (09:30 to 14:45 IST). Emits an unambiguous PASS or BLOCK
  verdict with detailed reasons and fingerprints each order in trader/state/risk.json.
  Use when the user asks to check trade risk, validate an order, review limits, or
  ensure compliance before submitting an order.
argument-hint: "[--orders FILE] [--now IST_TIME] [--no-write]"
---

# trader-risk

The Risk Manager protects capital by enforcing non-negotiable risk limits before
any order can reach the broker. An order that fails any single risk check is BLOCKED
with the exact reason.

This tool is not financial advice. No order is ever placed automatically. You must
explicitly say yes to any trade.

`${CLAUDE_SKILL_DIR}` below is this skill's folder.

```bash
python3 "${CLAUDE_SKILL_DIR}/check.py"                                 # checks trader/orders.json
python3 "${CLAUDE_SKILL_DIR}/check.py" --now "2026-10-19 10:15"        # test at specific time
python3 "${CLAUDE_SKILL_DIR}/check.py" --orders trader/orders.json --json
```

Flags: `--orders FILE`, `--nifty-filter` (block long breakouts if Nifty 50 < -0.30%, block short breakdowns if Nifty 50 > +0.30%),
`--now "YYYY-MM-DD HH:MM IST"`, `--no-write`, `--json`.
Exit code 0 when all orders PASS, 1 when any order is BLOCKED.

## What it reads and writes

| file | what |
| --- | --- |
| `trader/orders.json` | read: proposed bracket orders from trader-budget |
| `trader/config.json` | read: risk limits (max loss, daily loss, trading windows, `allow_short`, `nifty_filter`) |
| `trader/prices.json` | read: current prices and Nifty 50 index level |
| `trader/portfolio.json` | read: cash balance and open positions |
| `trader/state/broker.json` | read: orders placed today (for daily limits & duplicates) |
| `trader/state/risk.json` | written: cryptographic fingerprints and PASS/BLOCK verdicts |

## Rules Enforced
1. **Capital Risk**: `max_loss_per_trade_inr` and `max_daily_loss_inr`
2. **Stop Protection**: Mandatory stop-loss (lower than entry for buy, higher than entry for sell)
3. **Reward:Risk**: Minimum 1:1 reward-to-risk ratio
4. **Trading Window**: Entries permitted strictly during morning prime time (09:30 to 10:15 IST)
5. **Calendar**: Closed on weekends and official NSE trading holidays
6. **Market Trend**: Broad market filter (blocks aggressive breakout buys when Nifty 50 is trending down < -0.30%, blocks short breakdowns when Nifty 50 is trending up > +0.30%)
7. **Integrity**: No duplicates, no options, whole shares only
