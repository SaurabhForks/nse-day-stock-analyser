---
name: trader-budget
description: >-
  Budget Manager and Statutory Charges Calculator for Indian Equities (NSE & BSE).
  Sizes day trading positions in whole shares to your risk budget in Indian Rupees (₹),
  enforcing max loss limits and SEBI peak margin intraday leverage (5x). Automatically
  calculates full Indian statutory transaction charges (STT, NSE transaction charges,
  SEBI turnover fees, State Stamp Duty, GST, and discount brokerage), revealing true
  net breakeven points and net take-profit amounts. Writes trader/orders.json. Use
  when the user asks how many shares to buy, how to size an Indian stock trade, or
  what the taxes and brokerage charges will be.
argument-hint: "[--budget INR] [--max-loss INR] [--limit [PRICE]] [--write]"
---

# trader-budget

The Budget Manager converts your exit plan into a precise order size based on your
risk capital. In Indian equity trading, whole shares only are traded, and transaction
costs (STT, exchange fees, SEBI charges, stamp duty, GST) materially affect net returns.

This tool calculates every tax and fee down to the paisa and enforces your max loss rule.
Paper trading is enabled by default.

This tool is not financial advice. No order is ever placed automatically. You must
explicitly say yes to any trade.

`${CLAUDE_SKILL_DIR}` below is this skill's folder.

```bash
python3 "${CLAUDE_SKILL_DIR}/size.py"                                  # trader/plan.json + config.json
python3 "${CLAUDE_SKILL_DIR}/size.py" --write                          # writes trader/orders.json
python3 "${CLAUDE_SKILL_DIR}/size.py" --limit                          # limit order at plan entry
python3 "${CLAUDE_SKILL_DIR}/size.py" --budget 100000 --max-loss 1000  # override parameters
```

Flags: `--budget INR`, `--max-loss INR`, `--limit [PRICE]`, `--write`, `--json`.

## What it reads and writes

| file | what |
| --- | --- |
| `trader/plan.json` | read: entry price, stop-loss price, target price |
| `trader/config.json` | read: `budget_inr`, `max_loss_per_trade_inr`, `max_position_pct`, `intraday_leverage` |
| `trader/portfolio.json` | read: available cash balance |
| `trader/orders.json` | written: ready-to-check bracket order with share quantity and statutory fee breakdowns |

## Indian Statutory Taxes Calculated
- **STT (Securities Transaction Tax)**: 0.025% on sell turnover (intraday)
- **NSE Transaction Charge**: 0.00297% on total turnover
- **SEBI Turnover Fee**: ₹10 per crore (0.0001%)
- **Stamp Duty**: 0.003% on buy turnover
- **Brokerage**: ₹20 flat or 0.03% per executed order (discount broker standard)
- **GST**: 18% on (Brokerage + Exchange Fees + SEBI charges)
