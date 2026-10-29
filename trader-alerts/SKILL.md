---
name: trader-alerts
description: >-
  Price Alerts and Market Clock for Indian Equities (NSE & BSE). Tracks real-time
  prices for Indian stocks and rings when a target price, stop-loss, percentage move,
  or key market time is hit. Manages the Indian Standard Time (IST) market clock,
  recognizing official NSE holidays, pre-market sessions, opening bell (09:15 AM IST),
  broker MIS auto-square-off cutoff (15:15 PM IST), and normal market close (03:30 PM IST).
  Writes trader/prices.json and maintains trader/alerts.json. Use when the user asks
  for price alerts on an Indian stock, asks if NSE is open, or wants automated stop/target
  monitoring.
argument-hint: "[clock | quote | add | check | list | reset]"
---

# trader-alerts

Price Alerts and the NSE clock monitor real-time stock prices and trading day events.
Alerts fire once upon trigger and remain silent until reset or rearmed.

This tool is not financial advice. No order is ever placed automatically. You must
explicitly say yes to any trade.

`${CLAUDE_SKILL_DIR}` below is this skill's folder.

```bash
python3 "${CLAUDE_SKILL_DIR}/alerts.py" clock                          # check if NSE is open
python3 "${CLAUDE_SKILL_DIR}/alerts.py" quote RELIANCE --write         # write prices.json
python3 "${CLAUDE_SKILL_DIR}/alerts.py" quote --holdings --write       # quote portfolio & plan
python3 "${CLAUDE_SKILL_DIR}/alerts.py" add --from-plan                # stop, target, & flat-by
python3 "${CLAUDE_SKILL_DIR}/alerts.py" add --symbol RELIANCE --stop 2480.00
python3 "${CLAUDE_SKILL_DIR}/alerts.py" add --symbol RELIANCE --target 2540.00
python3 "${CLAUDE_SKILL_DIR}/alerts.py" add --at 15:15 --label "square off"
python3 "${CLAUDE_SKILL_DIR}/alerts.py" check                          # test if any alert rang
python3 "${CLAUDE_SKILL_DIR}/alerts.py" list                           # list active alerts
```

## What it reads and writes

| file | what |
| --- | --- |
| `trader/plan.json` | read by `add --from-plan`: stop price, target price, flat_by time |
| `trader/prices.json` | written: fresh market prices for watched tickers |
| `trader/alerts.json` | written: rule definitions and triggered states |

## Alert Types
- `above` / `target`: Fires when current price >= target price
- `below` / `stop`: Fires when current price <= stop-loss price
- `pct_move`: Fires when price moves >= X% from previous close
- `time`: Fires when IST clock reaches specified HH:MM
- `opening_bell`: Rings once per trading day at 09:15 AM IST
