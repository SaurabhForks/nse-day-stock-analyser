---
name: trader-insider
description: >-
  SEBI Insider Trading, Bulk Deals & Super Investor Tracker for Indian Equities.
  The Indian market counterpart to the US Pelosi tracker. Monitors official SEBI PIT
  (Prohibition of Insider Trading) filings by company promoters and directors, SEBI SAST
  takeover disclosures (>2% changes in shareholding), daily NSE/BSE Bulk & Block Deals
  disclosed at 15:45 IST, and portfolio movements of celebrated Indian 'Big Bull' super
  investors (Radhakishan Damani, Ashish Kacholia, Vijay Kedia, Mukul Agrawal, Dolly Khanna,
  and Rakesh Jhunjhunwala / RARE Enterprises), alongside daily FII & DII institutional flows.
  Use when the user asks what insiders are buying, asks about bulk/block deals, tracks
  big bull investors in India, or investigates institutional smart money flows.
argument-hint: "[index | bulk | super-investor | fii-dii | new] [--symbol SYMBOL]"
---

# trader-insider

The Insider & Big Bull Tracker monitors institutional smart money and promoter
disclosures in India. All data is derived from official statutory filings under
SEBI (Prohibition of Insider Trading) Regulations and exchange bulk deal reports.

This is public regulatory data, not non-public insider tips.

This tool is not financial advice. No order is ever placed automatically. You must
explicitly say yes to any trade.

`${CLAUDE_SKILL_DIR}` below is this skill's folder.

```bash
python3 "${CLAUDE_SKILL_DIR}/insider.py" index --symbol RELIANCE           # promoter & director filings
python3 "${CLAUDE_SKILL_DIR}/insider.py" bulk --date 2026-10-19            # daily bulk & block deals
python3 "${CLAUDE_SKILL_DIR}/insider.py" super-investor --name damani      # Radhakishan Damani portfolio
python3 "${CLAUDE_SKILL_DIR}/insider.py" super-investor --list             # list tracked Indian ace investors
python3 "${CLAUDE_SKILL_DIR}/insider.py" fii-dii                           # FII / DII net flows in ₹ Cr
python3 "${CLAUDE_SKILL_DIR}/insider.py" new                               # check new alerts
```

Flags: `--symbol SYMBOL`, `--date YYYY-MM-DD`, `--name INVESTOR`, `--offline FILE`, `--json`.

## What it reads and writes

| file | what |
| --- | --- |
| `trader/state/insider.json` | written by `new`: tracks seen filing IDs to avoid duplicate alerts |

## Subcommands
- `index`: SEBI PIT promoter buying, director acquisitions, and pledge changes
- `bulk`: Daily NSE & BSE Bulk Deals (> 0.5% equity) and Block Deals (> ₹10 Cr)
- `super-investor`: Disclosed portfolios and major stakes of iconic Indian super investors
- `fii-dii`: Daily Foreign and Domestic Institutional Investors gross & net flows in ₹ Crores
- `new`: Alerts on new insider filings since the last check
