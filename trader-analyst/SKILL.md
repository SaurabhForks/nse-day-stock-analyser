---
name: trader-analyst
description: >-
  Earnings Analyst and Ind-AS Financial Statement Reader for Indian Companies.
  Pulls audited quarterly results (Q1, Q2, Q3, Q4) and Annual Reports filed with NSE & BSE,
  summarizing revenue from operations, EBITDA, Profit After Tax (PAT), operating margins,
  diluted EPS, and YoY/QoQ growth rates formatted in Indian financial standard ₹ Crores (Cr).
  Computes Trailing Twelve Month (TTM) fundamental aggregates and writes trader/metrics.json.
  Use when the user asks for financial results of an Indian company, wants quarterly revenue
  growth, evaluates profit margins, or compares company earnings fundamentals.
argument-hint: "SYMBOL... [--quarters N] [--metrics FILE]"
---

# trader-analyst

The Earnings Analyst pulls reported financial numbers from corporate filings under
Indian Accounting Standards (Ind-AS) and summarizes what changed quarter by quarter.
Values are rendered in standard Indian crore units (₹ Cr; 1 Cr = ₹10,000,000).

Numbers only: this tool never gives financial advice or predicts stock prices.

`${CLAUDE_SKILL_DIR}` below is this skill's folder.

```bash
python3 "${CLAUDE_SKILL_DIR}/facts.py" RELIANCE                       # latest quarters
python3 "${CLAUDE_SKILL_DIR}/facts.py" TCS INFY --quarters 8          # compare 8 quarters
python3 "${CLAUDE_SKILL_DIR}/facts.py" RELIANCE --json                # JSON dump
python3 "${CLAUDE_SKILL_DIR}/facts.py" RELIANCE TCS --metrics trader/metrics.json
```

Flags: `--quarters N` (default 4), `--metrics FILE`, `--offline DIR`, `--json`.

## What it reads and writes

| file | what |
| --- | --- |
| `trader/metrics.json` | written with `--metrics`: TTM revenue, PAT, EPS, and margins per ticker |

## Metrics Formatted (in ₹ Crores)
- **Revenue from Operations**: Core operating turnover with YoY & QoQ growth %
- **EBITDA**: Operating profitability and EBITDA Margin %
- **PAT (Profit After Tax)**: Net profit after finance costs and taxes
- **Diluted EPS**: Earnings per share in rupees (₹)
- **TTM Summary**: 12-month aggregated fundamentals
