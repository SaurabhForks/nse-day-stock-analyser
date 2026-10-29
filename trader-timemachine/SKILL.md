---
name: trader-timemachine
description: >-
  Time Machine for Indian Equities (NSE & BSE). Replays planned day trades before
  risking a rupee: runs 10,000 Monte Carlo replays constructed from the stock's own
  5-minute bars over the past 60 trading sessions, alongside backtesting the exact setup
  across every historical session. Calibrated specifically to the Indian market session
  (75 five-minute bars from 09:15 to 15:30 IST) with conservative stop-first execution.
  Reports empirical target odds, stop odds, auto-square-off prices, expected R-multiple,
  and an objective mathematical verdict. Use when the user asks to backtest a trade,
  simulate outcomes, check win probabilities, or evaluate statistical expectancy on an NSE stock.
argument-hint: "[run | chart] [--seed N] [--replays N] [--write]"
---

# trader-timemachine

The Time Machine is an empirical reality check before you risk a rupee. It samples
the stock's own historical 5-minute volatility across 60 days to simulate 10,000 possible
afternoons from the moment of your entry.

The simulation is not a prediction: news, halts, or unexpected volatility can always
exceed recent history. It exists to verify whether your target and stop have positive expectancy.

This tool is not financial advice. No order is ever placed automatically. You must
explicitly say yes to any trade.

`${CLAUDE_SKILL_DIR}` below is this skill's folder.

```bash
python3 "${CLAUDE_SKILL_DIR}/timemachine.py" run                          # trader/plan.json, 10,000 replays, seed 19
python3 "${CLAUDE_SKILL_DIR}/timemachine.py" run --write                  # save trader/timemachine.json
python3 "${CLAUDE_SKILL_DIR}/timemachine.py" run --until 15:15            # stop at Indian MIS square-off
python3 "${CLAUDE_SKILL_DIR}/timemachine.py" run --seed 7 --replays 20000 # customized replays
python3 "${CLAUDE_SKILL_DIR}/timemachine.py" chart                        # view ASCII fan chart
```

Flags: `--replays 10000`, `--seed 19`, `--until HH:MM` (default 15:15 IST),
`--offline FILE`, `--write`, `--json`.

## What it reads and writes

| file | what |
| --- | --- |
| `trader/plan.json` | read: entry, stop, target, date, flat_by |
| `trader/timemachine.json` | written: detailed Monte Carlo odds, historical backtest stats, percentile price bands |

## Key Metrics Evaluated
- **Target Hit %**: Probability of reaching profit target before stop-loss.
- **Stop Hit %**: Probability of touching stop-loss before target.
- **Neither %**: Trade remains open at 15:15 IST auto-square-off time.
- **Historical Win Rate**: How often this exact rule succeeded on this stock over the last 60 sessions.
- **Expected R Multiple**: Average statistical outcome in R-multiples (-1.0 to +target_R).
