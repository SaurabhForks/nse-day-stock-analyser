---
name: trader-broker
description: >-
  Broker Order Executor and Ticket Manager for Indian Brokers. Translates risk-checked
  orders into execution tickets and standardized JSON payloads for Indian discount
  brokers including Zerodha Kite Connect, Groww, Angel One SmartAPI, Upstox, and Dhan.
  Enforces zero-ambiguity confirmation: strictly demands an explicit "yes" with the
  symbol or ticket number before any action. Never places an order on its own; paper
  trading simulation is enabled by default. Maintains an immutable decision log in
  trader/state/broker.json and generates MIS intraday auto-square-off sell orders.
  Use when the user asks to review order tickets, approve a trade, send an order to Zerodha,
  or flatten open intraday positions before market close.
argument-hint: "[show | approve | result | fill | flatten | log]"
---

# trader-broker

The Order Executor formats approved day trades for Indian brokers and logs execution
decisions. It never connects to live markets or places orders on its own: paper
trading simulation is default, and an order is executed only when you explicitly type "yes".

This tool is not financial advice. No order is ever placed automatically. You must
explicitly say yes to any trade.

`${CLAUDE_SKILL_DIR}` below is this skill's folder.

```bash
python3 "${CLAUDE_SKILL_DIR}/ticket.py" show                                     # show tickets
python3 "${CLAUDE_SKILL_DIR}/ticket.py" show --index 1 --json                    # print Zerodha Kite payload
python3 "${CLAUDE_SKILL_DIR}/ticket.py" approve --index 1 --reply "yes RELIANCE" # record user approval
python3 "${CLAUDE_SKILL_DIR}/ticket.py" result --index 1 --status placed --broker-id 241019001
python3 "${CLAUDE_SKILL_DIR}/ticket.py" flatten --symbol RELIANCE --qty 10       # square off before 15:15 IST
python3 "${CLAUDE_SKILL_DIR}/ticket.py" log                                      # print decision history
```

## What it reads and writes

| file | what |
| --- | --- |
| `trader/orders.json` | read: proposed orders from trader-budget |
| `trader/state/risk.json` | read: pre-trade risk verification status (must be PASS) |
| `trader/state/broker.json` | written: append-only decision log of approvals and executions |
| `trader/portfolio.json` | written: updated shares and cash balance on fills |

## Safety Controls
- **Explicit Confirmation**: Rejects "sure", "ok", "yes to all", or blanket approvals. Must explicitly type "yes" naming the stock.
- **Risk Verification**: Only orders with cryptographic fingerprint match in trader/state/risk.json that PASSED can be approved.
- **Paper Trading Default**: Simulated execution unless live MCP connector is configured.
