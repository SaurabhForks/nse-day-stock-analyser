---
name: trader-ui
description: Interactive Web Terminal and REST API server for the Intraday Day Stock Analyser. Features 5m/15m candlestick charting, Opening Range (OR) box overlays, VWAP, bi-directional ORB scanner, bracket orders, and time machine replay.
---

# Trader UI Skill

## Features
- **Intraday Candlestick Chart View**:
  - 5-minute and 15-minute intraday bars.
  - Visual **15m Opening Range (OR) Box (09:15-09:30 IST)** with OR-High, OR-Low, and OR-Midpoint lines.
  - **VWAP (Volume Weighted Average Price)** overlay.
  - **Prime Time Shading (09:30-10:15 IST)**.
  - Visual breakout levels, 2R targets, and trailing stop lines.
  - 5-minute volume histogram with rolling RVol surge indicators.
- **Bi-Directional ORB Scanner**:
  - Real-time scanner for Long Breakouts and Short Breakdowns.
- **Bracket Order Broker**:
  - Live MTM P&L, 15:15 IST auto-square-off alert, and exact intraday statutory charges.
- **Time Machine Replay Simulator**:
  - 7-month historical replay across April-October 2026.

## Launch Command
```bash
python3 trader-ui/server.py --port 8502
```
Open `http://localhost:8502` in your browser.
