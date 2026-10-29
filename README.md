# The Indian Day Trader skill

11 Claude skills for Indian stock market day trading: scan thousands of NSE/BSE charts, track breaking news, time every entry and exit, and replay every outcome before you risk a rupee.

Free, MIT, no signup, no API key required. Plain Python that reads free public data: Yahoo Finance NSE charts (`.NS`), NSE official equity lists, and statutory SEBI corporate filings.

One scans thousands of NSE charts for setups. Another tracks breaking news and corporate actions on every stock you watch. One watches an intraday setup bar by bar and tells you the moment to get in, and another sets your stop-loss and your target before you do. And the most powerful is the Time Machine: before you risk a single rupee, it replays the rest of the session 10,000 times from the stock's own recent 5-minute bars, plus every past day the same setup fired, and tells you the honest mathematical odds.

And no trade goes through until you say yes. Nothing in this pack can place an order on its own. Paper trading is the default.

## Install

Paste this into Claude:

```
https://github.com/SaurabhTomar/indian-day-trader-skill

install skill
```

Or as a plugin in Claude Code:

```
/plugin marketplace add SaurabhTomar/indian-day-trader-skill
/plugin install indian-day-trader-skill@indian-day-trader-skill
```

Or copy the folders directly into your skills directory:

```bash
git clone https://github.com/SaurabhTomar/indian-day-trader-skill.git
cp -r indian-day-trader-skill/trader-* ~/.claude/skills/
```

Project-local instead of global: copy the same folders into your repo's `.claude/skills/`.

The tools need Python 3.8 or newer. Nothing to pip install: zero external dependencies, 100% Python standard library.

## The eleven

| command | job | what it does |
| --- | --- | --- |
| `/trader-scanner` | Chart Scanner | Scans thousands of NSE charts for setups: 15-minute Opening Range Breakouts (ORB), 20-day highs, bull flags, oversold bounces. |
| `/trader-news` | News Monitor | Tracks breaking news and corporate announcements on every Indian stock you watch and flags what moves it. |
| `/trader-entry` | Entry Timer | Watches an NSE setup bar by bar and tells you the exact moment a breakout candle closes. |
| `/trader-exit` | Exit Planner | Sets your stop-loss and your target before you enter, with mandatory MIS flattening by 15:15 IST. |
| `/trader-timemachine` | Time Machine | Replays every possible outcome before you risk a rupee: 10,000 simulated Indian sessions plus historical backtests. |
| `/trader-risk` | Risk Manager | Checks every trade against your limits (rupee drawdown, SEBI peak margin, NSE session hours) and blocks violations. |
| `/trader-budget` | Budget Manager | Sizes position to your risk budget (₹) and calculates all Indian statutory charges (STT, NSE fees, SEBI, GST, stamp duty). |
| `/trader-broker` | Order Executor | Formats tickets for Indian brokers (Zerodha Kite, Groww, Angel One, Upstox, Dhan), paper trading by default, never without your yes. |
| `/trader-alerts` | Price Alerts | Rings when a target, stop-loss, 09:15 AM opening bell, or 15:15 PM MIS square-off time hits. |
| `/trader-analyst` | Earnings Analyst | Reads Ind-AS quarterly results and annual statements, formatting revenue, EBITDA, and PAT in ₹ Crores. |
| `/trader-insider` | Insider & Big Bull Tracker | Tracks SEBI PIT promoter buying, SAST takeover disclosures, daily Bulk/Block deals, and ace investor portfolios. |

## How to use it

Everything lands in a `trader/` folder in your project, and each skill reads what the previous one wrote:

```
scanner -> news -> entry -> exit -> timemachine -> budget -> risk -> broker   (one trade)
alerts: stop, target, flat by 15:15 IST                                       (while open)
news / analyst / insider                                                       (on schedule)
```

### An example: Reliance Industries (RELIANCE)
Real Indian market example:

1. **`/trader-scanner`** at 09:45 AM IST: of the 200 NSE charts scanned, RELIANCE closed above its 15-minute opening range (09:15 to 09:30 range: ₹2,480.00 to ₹2,510.00). The 09:40 candle closed at ₹2,518.00, +0.32% over the top.
2. **`/trader-news`**: headlines check confirms Q2 results: Net Profit up 12% to ₹18,500 Crore and a new green energy EPC order win.
3. **`/trader-entry`**: at 09:45 IST confirmed the completed 5-minute candle close at ₹2,518.00 with 1.4x volume expansion.
4. **`/trader-exit`**: sets the plan before entry: stop at the opening range midpoint, ₹2,495.00 (₹23.00 risk/share); target at 2R, ₹2,564.00; mandatory flat by 15:15 IST.
5. **`/trader-timemachine`**: replayed the afternoon 10,000 times using RELIANCE's own 5-minute volatility over the previous 60 sessions. Target first: 34.2%, Stop first: 26.5%, still open at 15:15 IST: 39.3%. Verdict: positive expectancy (+0.28 R).
6. **`/trader-budget`**: with a ₹1,00,000 budget and ₹1,000 max loss per trade: ₹1,000 / ₹23.00 = 43 shares. It computes exact Indian statutory taxes (STT: ₹27.56, NSE txn charge: ₹6.48, SEBI fee: ₹0.22, Stamp duty: ₹3.25, Brokerage: ₹40.00, GST: ₹8.41 -> Total charges: ₹85.92). Net breakeven: ₹2.00/share move.
7. **`/trader-risk`**: checks against rules: max loss ₹989.00 < ₹1,000 limit, trade window valid (09:45 IST), reward-to-risk 2.0 > 1.0 minimum -> PASS.
8. **`/trader-broker`**: presents the ticket. You type `yes RELIANCE`. The paper trade simulator logs execution, or passes the order to your Zerodha Kite Connect tool.
9. **`/trader-alerts`**: watches live quotes and rings on target ₹2,564.00, stop ₹2,495.00, or at 15:15 IST to square off whatever is still open.

## The tools

```bash
python3 trader-scanner/scan.py universe                                # build NSE equity universe
python3 trader-scanner/scan.py daily                                   # pre-market setups
python3 trader-scanner/scan.py orb --at 10:15                          # opening-range breakouts so far
python3 trader-news/news.py --tickers RELIANCE TCS INFY                # headlines, corporate actions
python3 trader-entry/entry.py check RELIANCE --setup orb               # waiting / triggered / expired
python3 trader-entry/entry.py watch RELIANCE --every 30                # bar by bar monitor
python3 trader-exit/exit.py plan --stop or-mid --target 2R --write     # -> trader/plan.json
python3 trader-timemachine/timemachine.py run --write                  # 10,000 replays + backtest
python3 trader-budget/size.py --write                                  # -> trader/orders.json
python3 trader-risk/check.py                                           # PASS / BLOCK per order
python3 trader-broker/ticket.py show                                   # order tickets, READY or not
python3 trader-alerts/alerts.py add --from-plan                        # stop, target, 15:15 square off
python3 trader-alerts/alerts.py check                                  # rings triggered alerts
python3 trader-analyst/facts.py RELIANCE                               # Ind-AS revenue, EBITDA, PAT in ₹ Cr
python3 trader-insider/insider.py super-investor --name damani         # Radhakishan Damani portfolio
python3 trader-insider/insider.py bulk                                 # daily NSE/BSE bulk & block deals
```

Run test suite:

```bash
python3 -m unittest discover -s tests -v
```

## Fine print

**Not financial advice.** This software reads public financial data and performs arithmetic. It does not predict future price movements. Most day traders lose money. Never trade money you cannot afford to lose.

**No trade goes through until you say yes.** Only `/trader-broker` can approve an order, and only after `/trader-risk` passes that exact order and you explicitly type "yes" naming the stock.

**Paper trading by default.** `"paper": true` is the default in `config.example.json`. All tools simulate executions safely unless explicitly configured with live credentials.

**Indian Intraday Margin (MIS) & SEBI Peak Margin.** SEBI peak margin rules require 100% upfront margin. Typical intraday MIS leverage on cash equity is up to 5x.

**Mandatory 15:15 IST Square-off.** Indian brokers automatically square off intraday MIS positions between 15:15 and 15:25 PM IST and levy penalty charges (e.g. ₹50+GST). `/trader-exit` and `/trader-alerts` enforce an exit at 15:15 IST to prevent auto-square-off charges.

**Taxes & Statutory Fees.** Equity intraday trading attracts STT (0.025% on sell side), exchange turnover fees, SEBI turnover fees, State Stamp Duty, and 18% GST on brokerage. All these are factored into `/trader-budget`.

## Files

```
trader-scanner/     SKILL.md, scan.py
trader-news/        SKILL.md, news.py
trader-entry/       SKILL.md, entry.py
trader-exit/        SKILL.md, exit.py
trader-timemachine/ SKILL.md, timemachine.py
trader-risk/        SKILL.md, check.py
trader-budget/      SKILL.md, size.py, config.example.json, targets.example.json
trader-broker/      SKILL.md, ticket.py, zerodha_mcp_config.example.json
trader-alerts/      SKILL.md, alerts.py, alerts.example.json
trader-analyst/     SKILL.md, facts.py, metrics.example.json
trader-insider/     SKILL.md, insider.py, super_investors.example.json
tests/              unittest suite + offline fixtures
```

MIT License. Designed for the Indian Stock Market (NSE & BSE).
