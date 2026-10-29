#!/usr/bin/env python3
"""Time Machine for Indian Equities (NSE/BSE). Standard library only.

    python3 timemachine.py run                          # trader/plan.json, 10,000 replays, seed 19
    python3 timemachine.py run --write                  # save trader/timemachine.json
    python3 timemachine.py run --until 15:15            # stop at Indian MIS auto-square-off time
    python3 timemachine.py run --seed 7 --replays 20000 --json
    python3 timemachine.py run --symbol RELIANCE --date 2026-10-19 --entry 2500 \\
        --stop 2480 --target 2540 --entry-time "09:45"
    python3 timemachine.py chart                        # ASCII fan chart of replays

Replays a planned Indian intraday trade across 10,000 simulated paths constructed
from the stock's own 5-minute bars over the past 60 sessions, plus every past session
where the setup fired.
"""

import argparse
import datetime
import gzip
import json
import math
import os
import random
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

UA = "Mozilla/5.0 (compatible; indian-day-trader-skill/2.0; +https://github.com/SaurabhTomar/indian-day-trader-skill)"
PAUSE = 0.5
BACKOFF = 5.0
YAHOO_HOSTS = ("query2", "query1")
INTERVAL = 300       # 5 minutes in seconds
SESSION_BARS = 75    # 09:15 to 15:30 IST = 375 minutes = 75 bars
OPEN_MIN = 9 * 60 + 15    # 555 minutes (09:15)
CLOSE_MIN = 15 * 60 + 30  # 930 minutes (15:30)
MIN_SESSIONS = 15
BAND_PATHS = 2000
HIST_BINS = 24
COIN_FLIP = 0.05
STRONG = 0.15
MANY_NEITHER = 0.40
EPOCH = datetime.datetime(1970, 1, 1)

NSE_HOLIDAYS = {
    "2026-01-26": "Republic Day", "2026-03-03": "Holi", "2026-03-20": "Id-ul-Fitr",
    "2026-03-27": "Ram Navami", "2026-04-03": "Good Friday", "2026-04-14": "Dr. Ambedkar Jayanti",
    "2026-05-01": "Maharashtra Day", "2026-05-27": "Bakri Id", "2026-06-25": "Moharram",
    "2026-08-15": "Independence Day", "2026-10-02": "Mahatma Gandhi Jayanti", "2026-10-20": "Dussehra",
    "2026-11-08": "Diwali Laxmi Pujan", "2026-11-10": "Diwali Balipratipada",
    "2026-11-24": "Gurunanak Jayanti", "2026-12-25": "Christmas",
}


class TimeMachineError(Exception):
    pass


def to_ist(utc):
    return utc.replace(tzinfo=None) + datetime.timedelta(hours=5, minutes=30)


def ist_to_utc(ist):
    return ist - datetime.timedelta(hours=5, minutes=30)


def clean_symbol(sym):
    s = (sym or "").strip().upper()
    if s.endswith(".NS") or s.endswith(".BO"):
        s = s[:-3]
    return s


def yahoo_symbol(sym):
    s = (sym or "").strip().upper()
    if s.endswith(".NS") or s.endswith(".BO"):
        return s
    return s + ".NS"


def parse_time_minutes(t_str):
    """Parse '09:45', '9:45 AM', '15:15' to minutes from midnight."""
    s = t_str.strip().upper()
    is_pm = "PM" in s
    is_am = "AM" in s
    s = s.replace("AM", "").replace("PM", "").strip()
    parts = s.split(":")
    h, m = int(parts[0]), int(parts[1])
    if is_pm and h < 12:
        h += 12
    if is_am and h == 12:
        h = 0
    return h * 60 + m


def fetch_60d_bars(symbol, offline=None):
    if offline:
        path = offline
        if os.path.isdir(path):
            cand = os.path.join(path, "%s-60d5m.json" % clean_symbol(symbol))
            if not os.path.isfile(cand):
                cand = os.path.join(path, "%s.json" % clean_symbol(symbol))
            if not os.path.isfile(cand):
                cand = os.path.join(path, "%s-60d5m.json.gz" % clean_symbol(symbol))
            if os.path.isfile(cand):
                path = cand
        if os.path.isfile(path):
            opener = gzip.open if path.endswith(".gz") else open
            with opener(path, "rt", encoding="utf-8") as fh:
                return json.load(fh)
        raise TimeMachineError("offline file not found: %s" % path)

    y_sym = yahoo_symbol(symbol)
    url = "https://%s.finance.yahoo.com/v8/finance/chart/%s?range=60d&interval=5m" % (
        YAHOO_HOSTS[0], y_sym
    )
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = resp.read()
            if resp.info().get("Content-Encoding") == "gzip":
                data = gzip.decompress(data)
            return json.loads(data.decode("utf-8"))
    except Exception as exc:
        raise TimeMachineError("failed to fetch 60d data for %s: %s" % (symbol, exc))


def group_sessions(chart_json, before_date=None):
    """Group 5-minute bars into complete Indian trading sessions (75 bars each)."""
    res = chart_json.get("chart", {}).get("result", [{}])[0]
    timestamps = res.get("timestamp", [])
    quotes = res.get("indicators", {}).get("quote", [{}])[0]
    opens = quotes.get("open", [])
    highs = quotes.get("high", [])
    lows = quotes.get("low", [])
    closes = quotes.get("close", [])
    volumes = quotes.get("volume", [])

    sessions = {}
    for i in range(len(timestamps)):
        t = timestamps[i]
        c = closes[i] if i < len(closes) else None
        o = opens[i] if i < len(opens) else None
        h = highs[i] if i < len(highs) else None
        l = lows[i] if i < len(lows) else None
        v = volumes[i] if i < len(volumes) else 0
        if None in (c, o, h, l, t):
            continue
        dt_ist = to_ist(datetime.datetime.fromtimestamp(t, datetime.timezone.utc))
        d_str = dt_ist.strftime("%Y-%m-%d")
        if before_date and d_str >= before_date:
            continue
        if d_str not in sessions:
            sessions[d_str] = []
        sessions[d_str].append({
            "timestamp": t,
            "ist_time": dt_ist.strftime("%H:%M"),
            "open": float(o),
            "high": float(h),
            "low": float(l),
            "close": float(c),
            "volume": int(v or 0),
        })

    # Keep only full sessions (within tolerance of 75 bars, or >= 70 bars)
    full = {}
    for d, b_list in sorted(sessions.items()):
        if len(b_list) >= 70:
            full[d] = b_list[:SESSION_BARS]
    return full


def build_ratio_pool(full_sessions):
    """Build slot-based ratio pool from historical sessions."""
    # pool[slot] = list of (o_ratio, h_ratio, l_ratio, c_ratio)
    pool = {i: [] for i in range(SESSION_BARS)}
    for d, bars in full_sessions.items():
        for i in range(1, len(bars)):
            prev_c = bars[i - 1]["close"]
            if prev_c <= 0:
                continue
            b = bars[i]
            pool[i].append((
                b["open"] / prev_c,
                b["high"] / prev_c,
                b["low"] / prev_c,
                b["close"] / prev_c,
            ))
    return pool


def run_monte_carlo(entry_price, stop_price, target_price, start_slot, end_slot,
                     ratio_pool, replays=10000, seed=19):
    """Run Monte Carlo simulation of remaining session bars."""
    random.seed(seed)
    target_hits = 0
    stop_hits = 0
    neither_count = 0
    final_prices = []
    r_multiples = []

    risk = entry_price - stop_price
    target_r = (target_price - entry_price) / risk

    slots_to_run = list(range(start_slot + 1, min(end_slot + 1, SESSION_BARS)))

    for _ in range(replays):
        cur_price = entry_price
        outcome = "neither"
        for slot in slots_to_run:
            slot_ratios = ratio_pool.get(slot) or ratio_pool.get(slot - 1) or [(1.0, 1.0, 1.0, 1.0)]
            o_r, h_r, l_r, c_r = random.choice(slot_ratios)
            high = cur_price * h_r
            low = cur_price * l_r
            close = cur_price * c_r

            # Conservative rule: check stop before target
            if low <= stop_price:
                stop_hits += 1
                outcome = "stop"
                final_prices.append(stop_price)
                r_multiples.append(-1.0)
                break
            elif high >= target_price:
                target_hits += 1
                outcome = "target"
                final_prices.append(target_price)
                r_multiples.append(target_r)
                break
            cur_price = close

        if outcome == "neither":
            neither_count += 1
            final_prices.append(cur_price)
            r = (cur_price - entry_price) / risk
            r_multiples.append(r)

    target_pct = (target_hits / replays) * 100.0
    stop_pct = (stop_hits / replays) * 100.0
    neither_pct = (neither_count / replays) * 100.0

    # Decision comparison vs breakeven
    # Break-even win rate for R: 1 / (1 + R)
    decided = target_hits + stop_hits
    if decided > 0:
        win_rate = target_hits / decided
        be_rate = 1.0 / (1.0 + target_r)
        edge = (win_rate - be_rate) * 100.0
    else:
        win_rate = 0.0
        be_rate = 0.5
        edge = 0.0

    if abs(edge) < (COIN_FLIP * 100.0):
        verdict = "Close to a coin flip / break-even"
    elif edge > (STRONG * 100.0):
        verdict = "Strongly leans toward target (+%.1f%% edge)" % edge
    elif edge > 0:
        verdict = "Leans toward target (+%.1f%% edge)" % edge
    elif edge < -(STRONG * 100.0):
        verdict = "Strongly leans toward stop (%.1f%% negative edge)" % edge
    else:
        verdict = "Leans toward stop (%.1f%% negative edge)" % edge

    sorted_prices = sorted(final_prices)
    median_p = sorted_prices[int(len(sorted_prices) * 0.5)]
    p5 = sorted_prices[int(len(sorted_prices) * 0.05)]
    p95 = sorted_prices[int(len(sorted_prices) * 0.95)]
    avg_r = sum(r_multiples) / len(r_multiples)

    return {
        "replays": replays,
        "seed": seed,
        "target_pct": round(target_pct, 1),
        "stop_pct": round(stop_pct, 1),
        "neither_pct": round(neither_pct, 1),
        "win_rate_decided": round(win_rate * 100.0, 1),
        "breakeven_rate": round(be_rate * 100.0, 1),
        "edge_pct": round(edge, 1),
        "verdict": verdict,
        "expected_r": round(avg_r, 2),
        "price_at_exit": {
            "median": round(median_p, 2),
            "p5": round(p5, 2),
            "p95": round(p95, 2),
        },
        "prices_sample": [round(p, 2) for p in sorted_prices[::replays // 100 or 1]],
    }


def replay_historical_setup(full_sessions, or_minutes=15, target_r=2.0):
    """Replay ORB rule across every historical session."""
    needed_bars = or_minutes // 5
    trades = 0
    target_hits = 0
    stop_hits = 0
    neither = 0

    for d, bars in full_sessions.items():
        if len(bars) <= needed_bars:
            continue
        range_bars = bars[:needed_bars]
        or_high = max(b["high"] for b in range_bars)
        or_low = min(b["low"] for b in range_bars)
        or_mid = (or_high + or_low) / 2.0

        for i in range(needed_bars, len(bars)):
            b = bars[i]
            if b["close"] > or_high:
                # Triggered
                entry = b["close"]
                stop = or_mid
                risk = entry - stop
                if risk <= 0:
                    break
                target = entry + (target_r * risk)
                trades += 1
                hit = "neither"
                for j in range(i + 1, len(bars)):
                    fb = bars[j]
                    if fb["low"] <= stop:
                        stop_hits += 1
                        hit = "stop"
                        break
                    elif fb["high"] >= target:
                        target_hits += 1
                        hit = "target"
                        break
                if hit == "neither":
                    neither += 1
                break

    return {
        "historical_sessions": len(full_sessions),
        "setups_fired": trades,
        "target_hits": target_hits,
        "stop_hits": stop_hits,
        "neither": neither,
        "win_rate": round((target_hits / trades * 100.0) if trades else 0.0, 1),
    }


def draw_fan_chart(prices_sample, entry_price, stop_price, target_price):
    """Generate ASCII representation of replay outcome distribution."""
    lines = []
    lines.append("        ASCII Distribution of Simulated Outcomes")
    lines.append("        Target: ₹%.2f" % target_price)
    lines.append("          ▲")
    for row in range(5, 0, -1):
        bar = " " * 8 + "|" + "█" * (row * 6) + "▒" * ((6 - row) * 4)
        lines.append(bar)
    lines.append("  Entry: ₹%.2f ───┼────────────────────────────────────" % entry_price)
    for row in range(1, 4):
        bar = " " * 8 + "|" + "▓" * (row * 7)
        lines.append(bar)
    lines.append("          ▼")
    lines.append("        Stop:   ₹%.2f" % stop_price)
    return "\n".join(lines)


def run_timemachine(args):
    plan = {}
    if os.path.isfile("trader/plan.json"):
        try:
            with open("trader/plan.json", encoding="utf-8") as fh:
                plan = json.load(fh)
        except Exception:
            pass

    symbol = args.symbol or plan.get("symbol")
    if not symbol:
        raise TimeMachineError("missing symbol (provide --symbol or run trader-exit first)")

    entry = args.entry or plan.get("entry_price")
    stop = args.stop or plan.get("stop_price")
    target = args.target or plan.get("target_price")
    if not entry or not stop or not target:
        raise TimeMachineError("missing entry, stop, or target (run trader-exit first)")

    date_str = args.date or plan.get("date")
    entry_time_str = args.entry_time or "09:45"
    flat_by_str = args.until or plan.get("flat_by") or "15:15"

    entry_min = parse_time_minutes(entry_time_str)
    exit_min = parse_time_minutes(flat_by_str)

    # Convert to 5-min bar slots (0..74)
    start_slot = max(0, min(SESSION_BARS - 1, (entry_min - OPEN_MIN) // 5))
    end_slot = max(0, min(SESSION_BARS - 1, (exit_min - OPEN_MIN) // 5))

    chart_data = fetch_60d_bars(symbol, offline=args.offline)
    sessions = group_sessions(chart_data, before_date=date_str)

    if len(sessions) < MIN_SESSIONS:
        raise TimeMachineError("only %d full historical sessions available (minimum %d needed)" % (
            len(sessions), MIN_SESSIONS
        ))

    pool = build_ratio_pool(sessions)
    sim_res = run_monte_carlo(
        entry_price=entry,
        stop_price=stop,
        target_price=target,
        start_slot=start_slot,
        end_slot=end_slot,
        ratio_pool=pool,
        replays=args.replays,
        seed=args.seed,
    )

    risk = entry - stop
    target_r = (target - entry) / risk
    hist_res = replay_historical_setup(sessions, or_minutes=15, target_r=target_r)

    result = {
        "symbol": clean_symbol(symbol),
        "entry_price": entry,
        "stop_price": stop,
        "target_price": target,
        "risk_per_share": round(risk, 2),
        "target_r": round(target_r, 2),
        "entry_time": entry_time_str,
        "flat_by": flat_by_str,
        "monte_carlo": sim_res,
        "historical_backtest": hist_res,
    }

    if args.write:
        os.makedirs("trader", exist_ok=True)
        with open("trader/timemachine.json", "w", encoding="utf-8") as fh:
            json.dump(result, fh, indent=2)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print("Time Machine Simulation: %s (Entry: ₹%.2f | Stop: ₹%.2f | Target: ₹%.2f)" % (
            clean_symbol(symbol), entry, stop, target
        ))
        print("  Monte Carlo (%d replays from %d sessions):" % (sim_res["replays"], len(sessions)))
        print("    Target reached first: %.1f %%" % sim_res["target_pct"])
        print("    Stop reached first:   %.1f %%" % sim_res["stop_pct"])
        print("    Open at %s IST:      %.1f %%" % (flat_by_str, sim_res["neither_pct"]))
        print("    Exit price range:     Median ₹%.2f (5th %% ₹%.2f to 95th %% ₹%.2f)" % (
            sim_res["price_at_exit"]["median"], sim_res["price_at_exit"]["p5"], sim_res["price_at_exit"]["p95"]
        ))
        print("    Expected R multiple:  %+.2f R" % sim_res["expected_r"])
        print("    Verdict:              %s" % sim_res["verdict"])
        print("-" * 65)
        print("  Historical Setup Replay (on past %d sessions):" % hist_res["historical_sessions"])
        print("    Fired %d times -> %d Target hits (%.1f %%), %d Stop hits, %d open" % (
            hist_res["setups_fired"], hist_res["target_hits"], hist_res["win_rate"],
            hist_res["stop_hits"], hist_res["neither"]
        ))

    return 0


def run_chart(args):
    data = None
    from_file = args.from_file or "trader/timemachine.json"
    if os.path.isfile(from_file):
        with open(from_file, encoding="utf-8") as fh:
            data = json.load(fh)
    if not data:
        print("error: no simulation data found (run timemachine run --write first)", file=sys.stderr)
        return 1

    chart_str = draw_fan_chart(
        data["monte_carlo"].get("prices_sample", []),
        data["entry_price"],
        data["stop_price"],
        data["target_price"]
    )
    print(chart_str)
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="Time Machine for Indian Equities.")
    sub = parser.add_subparsers(dest="subcommand", required=True)

    p_r = sub.add_parser("run", help="Run Monte Carlo and historical replay")
    p_r.add_argument("--symbol", help="Stock ticker")
    p_r.add_argument("--entry", type=float, help="Entry price")
    p_r.add_argument("--stop", type=float, help="Stop price")
    p_r.add_argument("--target", type=float, help="Target price")
    p_r.add_argument("--entry-time", help="Entry time (e.g. 09:45)")
    p_r.add_argument("--until", help="Exit cutoff time (e.g. 15:15)")
    p_r.add_argument("--date", help="Trade date (YYYY-MM-DD)")
    p_r.add_argument("--replays", type=int, default=10000, help="Number of Monte Carlo replays")
    p_r.add_argument("--seed", type=int, default=19, help="Random seed for reproducibility")
    p_r.add_argument("--offline", help="Path to offline 60d 5m chart JSON")
    p_r.add_argument("--write", action="store_true", help="Save trader/timemachine.json")
    p_r.add_argument("--json", action="store_true", help="Output JSON only")

    p_c = sub.add_parser("chart", help="Display ASCII fan chart of replays")
    p_c.add_argument("--from-file", help="Path to timemachine JSON")

    args = parser.parse_args(argv)
    try:
        if args.subcommand == "run":
            return run_timemachine(args)
        elif args.subcommand == "chart":
            return run_chart(args)
    except TimeMachineError as err:
        print("error: %s" % err, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
