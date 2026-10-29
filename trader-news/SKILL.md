---
name: trader-news
description: >-
  News Monitor and Corporate Actions Tracker for Indian Equities (NSE & BSE).
  Tracks breaking news, earnings announcements (Q1-Q4 results), board meetings,
  dividends, order wins, promoter block/bulk deals, and SEBI regulatory filings
  for stocks on your watchlist, planned trades, and current portfolio. Tags items
  by market impact catalyst and flags volatile price moves in Indian Standard Time (IST).
  Use when the user asks for news on Indian stocks, corporate announcements, earnings
  results, order wins, or catalyst checks before entering an NSE day trade.
argument-hint: "[--tickers SYMBOL...] [--hours N]"
---

# trader-news

The News Monitor tracks catalysts that move Indian stocks. It pulls feeds from
Yahoo Finance India and regulatory announcement feeds, tagging items with
categories like earnings, dividends, order wins, SEBI actions, and promoter deals.

This tool is not financial advice. Headlines are news leads, not trade signals.

`${CLAUDE_SKILL_DIR}` below is this skill's folder.

```bash
python3 "${CLAUDE_SKILL_DIR}/news.py"                                  # watchlist + plan + portfolio
python3 "${CLAUDE_SKILL_DIR}/news.py" --tickers RELIANCE TCS INFY      # specific stocks
python3 "${CLAUDE_SKILL_DIR}/news.py" --tickers TATAMOTORS --hours 72  # last 3 days
python3 "${CLAUDE_SKILL_DIR}/news.py" --no-moves                       # skip price change calculation
```

Flags: `--hours N` (default 24), `--all` (print seen headlines too), `--no-moves`,
`--offline DIR`, `--json`.

## What it reads and writes

| file | what |
| --- | --- |
| `trader/watchlist.json` | read: tickers from scanner hits |
| `trader/plan.json` | read: ticker of the current planned trade |
| `trader/portfolio.json` | read: open positions |
| `trader/state/news.json` | written: tracks seen headlines so each item alerts once |

## Catalysts Tagged
- `results`: Quarterly results, revenue, PAT, EBITDA, margins
- `corporate_action`: Dividends, bonus shares, stock splits, buybacks
- `orders`: Major contract awards, defense tenders, railway EPC orders
- `regulatory`: SEBI inquiries, penalties, show-cause notices, NCLT proceedings
- `promoter_deal`: Promoter stake sales/purchases, pledging, bulk/block deals
- `management`: CEO/MD appointments, CFO resignations, statutory auditor changes
- `circuit_halt`: Upper/lower circuit limits hit, trading suspensions
