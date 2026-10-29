#!/usr/bin/env python3
"""Entry Timer for Indian equities (NSE/BSE). Standard library only.

    python3 entry.py check RELIANCE                      # opening-range breakout, 5-minute bars
    python3 entry.py check RELIANCE --now "2026-10-19 10:15" --offline RELIANCE.json
    python3 entry.py check TCS --setup level --level 3750.00   # first close above a level
    python3 entry.py check INFY --interval 5m --min-volume-x 1.2 --write
    python3 entry.py watch RELIANCE --every 30 --until 14:45   # poll bar by bar until trigger
    python3 entry.py watchlist                                # every hit in trader/watchlist.json

Watches bar by bar for an entry trigger during the Indian trading session (09:15 to 15:30 IST).
Writes trader/entry.json when triggered. Longs only. Never places an order.
"""

import argparse
import datetime
import gzip
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
import ssl

try:
    import certifi
    SSL_CTX = ssl.create_default_context(cafile=certifi.where())
except Exception:
    SSL_CTX = ssl._create_unverified_context()

UA = "Mozilla/5.0 (compatible; indian-day-trader-skill/2.0; +https://github.com/SaurabhTomar/indian-day-trader-skill)"
PAUSE = 0.5
BACKOFF = 5.0
GRACE = 2
SETTLE = 60
YAHOO_HOSTS = ("query2", "query1")
INTERVALS = {"1m": 60, "5m": 300}
DEFAULTS = {"no_entries_before": "09:30", "no_entries_after": "10:15"}

NSE_HOLIDAYS = {
    "2026-01-26": "Republic Day",
    "2026-03-03": "Holi",
    "2026-03-20": "Id-ul-Fitr",
    "2026-03-27": "Ram Navami",
    "2026-04-03": "Good Friday",
    "2026-04-14": "Dr. Ambedkar Jayanti",
    "2026-05-01": "Maharashtra Day",
    "2026-05-27": "Bakri Id",
    "2026-06-25": "Moharram",
    "2026-08-15": "Independence Day",
    "2026-10-02": "Mahatma Gandhi Jayanti",
    "2026-10-20": "Dussehra",
    "2026-11-08": "Diwali Laxmi Pujan (Muhurat Trading)",
    "2026-11-10": "Diwali Balipratipada",
    "2026-11-24": "Gurunanak Jayanti",
    "2026-12-25": "Christmas",
}


class EntryError(Exception):
    pass


def to_ist(utc):
    """UTC -> IST (UTC+05:30)."""
    return utc.replace(tzinfo=None) + datetime.timedelta(hours=5, minutes=30)


def ist_to_utc(ist):
    """IST -> UTC."""
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


def parse_now(text):
    if not text:
        return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0, tzinfo=None)
    t = text.strip().replace("Z", "+00:00")
    try:
        dt = datetime.datetime.fromisoformat(t)
    except ValueError:
        for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                dt = datetime.datetime.strptime(t, fmt)
                break
            except ValueError:
                pass
        else:
            raise EntryError("cannot parse date/time: %r" % text)
    if dt.tzinfo is not None:
        return dt.astimezone(datetime.timezone.utc).replace(microsecond=0, tzinfo=None)
    return ist_to_utc(dt).replace(microsecond=0)


def fetch_chart(symbol, interval="5m", offline=None):
    if offline:
        path = offline
        if os.path.isdir(path):
            cand = os.path.join(path, "%s.json" % clean_symbol(symbol))
            if not os.path.isfile(cand):
                cand = os.path.join(path, "%s.NS.json" % clean_symbol(symbol))
            if os.path.isfile(cand):
                path = cand
        if os.path.isfile(path):
            opener = gzip.open if path.endswith(".gz") else open
            with opener(path, "rt", encoding="utf-8") as fh:
                return json.load(fh)
        raise EntryError("offline file not found: %s" % path)

    y_sym = yahoo_symbol(symbol)
    url = "https://%s.finance.yahoo.com/v8/finance/chart/%s?range=1d&interval=%s" % (
        YAHOO_HOSTS[0], y_sym, interval
    )
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10, context=SSL_CTX) as resp:
            data = resp.read()
            if resp.info().get("Content-Encoding") == "gzip":
                data = gzip.decompress(data)
            return json.loads(data.decode("utf-8"))
    except Exception as exc:
        raise EntryError("failed to fetch chart for %s: %s" % (symbol, exc))


def parse_bars(chart_json, interval_sec=300, cutoff_utc=None):
    res = chart_json.get("chart", {}).get("result", [{}])[0]
    timestamps = res.get("timestamp", [])
    quotes = res.get("indicators", {}).get("quote", [{}])[0]
    opens = quotes.get("open", [])
    highs = quotes.get("high", [])
    lows = quotes.get("low", [])
    closes = quotes.get("close", [])
    volumes = quotes.get("volume", [])

    cutoff_ts = cutoff_utc.replace(tzinfo=datetime.timezone.utc).timestamp() if cutoff_utc else float("inf")
    bars = []

    for i in range(len(timestamps)):
        t = timestamps[i]
        c = closes[i] if i < len(closes) else None
        o = opens[i] if i < len(opens) else None
        h = highs[i] if i < len(highs) else None
        l = lows[i] if i < len(lows) else None
        v = volumes[i] if i < len(volumes) else 0
        if None in (c, o, h, l, t):
            continue
        # Only closed bars count
        if t + interval_sec > cutoff_ts:
            continue
        dt_ist = to_ist(datetime.datetime.fromtimestamp(t, datetime.timezone.utc))
        bars.append({
            "timestamp": t,
            "ist_time": dt_ist.strftime("%H:%M"),
            "date": dt_ist.strftime("%Y-%m-%d"),
            "open": float(o),
            "high": float(h),
            "low": float(l),
            "close": float(c),
            "volume": int(v or 0),
        })
    return bars


def compute_vwap(bars):
    """Compute Volume-Weighted Average Price (VWAP) across bars.
    Typical price = (high + low + close) / 3.0
    VWAP = sum(typical_price * volume) / sum(volume)
    """
    total_vol = 0
    total_pv = 0.0
    for b in bars:
        v = b.get("volume", 0)
        if v <= 0:
            continue
        tp = (b["high"] + b["low"] + b["close"]) / 3.0
        total_pv += tp * v
        total_vol += v
    if total_vol == 0:
        return None
    return total_pv / total_vol


def evaluate_entry(symbol, bars, setup="orb", level=None, or_minutes=15, min_vol_x=1.0,
                   rvol_mult=1.0, min_or_width_pct=0.4, max_or_width_pct=2.0,
                   min_close_pos=0.65, max_upper_wick=0.35, max_lower_wick=0.35,
                   require_vwap=True, window_start="09:30", window_end="10:15",
                   direction="long"):
    """Evaluate whether an entry triggered (long, short, or both)."""
    if not bars:
        return {"status": "no-data", "reason": "no closed bars available"}

    date_str = bars[0]["date"]
    last_bar = bars[-1]
    last_time = last_bar["ist_time"]

    # Opening Range Breakout (ORB)
    if setup == "orb":
        needed_bars = or_minutes // 5
        if len(bars) < needed_bars:
            return {"status": "waiting", "reason": "opening range still forming (bar %d of %d)" % (len(bars), needed_bars)}

        range_bars = bars[:needed_bars]
        or_high = max(b["high"] for b in range_bars)
        or_low = min(b["low"] for b in range_bars)
        avg_or_vol = sum(b["volume"] for b in range_bars) / len(range_bars)
        or_width_pct = ((or_high - or_low) / or_low) * 100.0 if or_low > 0 else 0.0

        if min_or_width_pct is not None and or_width_pct < min_or_width_pct:
            return {
                "status": "waiting",
                "reason": "opening range too narrow (%.2f%% < %.2f%% minimum volatility)" % (
                    or_width_pct, min_or_width_pct
                ),
            }
        if max_or_width_pct is not None and or_width_pct > max_or_width_pct:
            return {
                "status": "waiting",
                "reason": "opening range too wide / exhausted (%.2f%% > %.2f%% maximum volatility)" % (
                    or_width_pct, max_or_width_pct
                ),
            }

        # Check completed bars after the range
        for idx in range(needed_bars, len(bars)):
            b = bars[idx]
            b_time = b["ist_time"]
            if b_time < window_start:
                continue
            if b_time > window_end:
                break

            prev_bars = bars[max(0, idx - 5):idx]
            avg_5b_vol = (sum(pb["volume"] for pb in prev_bars) / len(prev_bars)) if prev_bars else avg_or_vol
            rvol = round(b["volume"] / avg_5b_vol, 2) if avg_5b_vol > 0 else 1.0
            vwap = compute_vwap(bars[:idx + 1])
            c_rng = b["high"] - b["low"]
            c_pos = ((b["close"] - b["low"]) / c_rng) if c_rng > 0 else 1.0
            u_wick = ((b["high"] - max(b["close"], b.get("open", b["close"]))) / c_rng) if c_rng > 0 else 0.0
            l_wick = ((min(b["close"], b.get("open", b["close"])) - b["low"]) / c_rng) if c_rng > 0 else 0.0

            # 1. LONG Breakout
            if direction in ("long", "both") and b["close"] > or_high:
                if min_vol_x > 1.0 and b["volume"] < (avg_or_vol * min_vol_x):
                    continue
                if rvol_mult > 1.0 and avg_5b_vol > 0 and b["volume"] < (avg_5b_vol * rvol_mult):
                    continue
                if require_vwap and vwap is not None and b["close"] < vwap:
                    continue
                if min_close_pos is not None and c_pos < min_close_pos:
                    continue
                if max_upper_wick is not None and u_wick > max_upper_wick:
                    continue

                pct_over = ((b["close"] - or_high) / or_high) * 100.0
                return {
                    "status": "triggered",
                    "symbol": clean_symbol(symbol),
                    "setup": "orb",
                    "side": "buy",
                    "direction": "long",
                    "date": date_str,
                    "trigger_time": b_time + " IST",
                    "trigger_bar_time": b_time,
                    "entry_price": round(b["close"], 2),
                    "or_high": round(or_high, 2),
                    "or_low": round(or_low, 2),
                    "or_width_pct": round(or_width_pct, 2),
                    "close_pos_pct": round(c_pos * 100.0, 1),
                    "upper_wick_pct": round(u_wick * 100.0, 1),
                    "vwap": round(vwap, 2) if vwap is not None else None,
                    "rvol": rvol,
                    "pct_over": round(pct_over, 2),
                    "volume": b["volume"],
                    "avg_or_volume": int(avg_or_vol),
                    "avg_5bar_volume": int(avg_5b_vol),
                }

            # 2. SHORT Breakdown
            elif direction in ("short", "both") and b["close"] < or_low:
                if min_vol_x > 1.0 and b["volume"] < (avg_or_vol * min_vol_x):
                    continue
                if rvol_mult > 1.0 and avg_5b_vol > 0 and b["volume"] < (avg_5b_vol * rvol_mult):
                    continue
                if require_vwap and vwap is not None and b["close"] > vwap:
                    continue
                # Close must be near the bottom of candle (e.g. <= 0.35)
                max_short_pos = (1.0 - min_close_pos) if min_close_pos is not None else 0.35
                if c_pos > max_short_pos:
                    continue
                if max_lower_wick is not None and l_wick > max_lower_wick:
                    continue

                pct_under = ((or_low - b["close"]) / or_low) * 100.0
                return {
                    "status": "triggered",
                    "symbol": clean_symbol(symbol),
                    "setup": "orb",
                    "side": "sell",
                    "direction": "short",
                    "date": date_str,
                    "trigger_time": b_time + " IST",
                    "trigger_bar_time": b_time,
                    "entry_price": round(b["close"], 2),
                    "or_high": round(or_high, 2),
                    "or_low": round(or_low, 2),
                    "or_width_pct": round(or_width_pct, 2),
                    "close_pos_pct": round(c_pos * 100.0, 1),
                    "lower_wick_pct": round(l_wick * 100.0, 1),
                    "vwap": round(vwap, 2) if vwap is not None else None,
                    "rvol": rvol,
                    "pct_under": round(pct_under, 2),
                    "volume": b["volume"],
                    "avg_or_volume": int(avg_or_vol),
                    "avg_5bar_volume": int(avg_5b_vol),
                }

        if last_time >= window_end:
            return {"status": "expired", "reason": "no trigger before %s IST" % window_end}
        if direction == "short":
            return {"status": "waiting", "reason": "no close below range low ₹%.2f yet" % or_low}
        elif direction == "both":
            return {"status": "waiting", "reason": "price inside range [₹%.2f - ₹%.2f]" % (or_low, or_high)}
        return {"status": "waiting", "reason": "no close above range high ₹%.2f yet" % or_high}

    # Static Level Setup
    elif setup == "level":
        if level is None:
            raise EntryError("level setup requires --level PRICE")
        target_lvl = float(level)
        for idx in range(len(bars)):
            b = bars[idx]
            b_time = b["ist_time"]
            if b_time < window_start:
                continue
            if b_time > window_end:
                break
            if b["close"] > target_lvl:
                vwap = compute_vwap(bars[:idx + 1])
                if require_vwap and vwap is not None and b["close"] < vwap:
                    continue
                pct_over = ((b["close"] - target_lvl) / target_lvl) * 100.0
                return {
                    "status": "triggered",
                    "symbol": clean_symbol(symbol),
                    "setup": "level",
                    "date": date_str,
                    "trigger_time": b_time + " IST",
                    "trigger_bar_time": b_time,
                    "entry_price": round(b["close"], 2),
                    "level": round(target_lvl, 2),
                    "vwap": round(vwap, 2) if vwap is not None else None,
                    "pct_over": round(pct_over, 2),
                    "volume": b["volume"],
                }

        if last_time >= window_end:
            return {"status": "expired", "reason": "no trigger before %s IST" % window_end}
        return {"status": "waiting", "reason": "no close above level ₹%.2f yet" % target_lvl}

    raise EntryError("unknown setup: %s" % setup)


def run_check(args):
    now_utc = parse_now(args.now)
    chart = fetch_chart(args.symbol, interval=args.interval, offline=args.offline)
    interval_sec = INTERVALS.get(args.interval, 300)
    bars = parse_bars(chart, interval_sec=interval_sec, cutoff_utc=now_utc)

    # Read config if present
    cfg = {}
    if os.path.isfile("trader/config.json"):
        try:
            with open("trader/config.json", encoding="utf-8") as fh:
                cfg = json.load(fh)
        except Exception:
            pass

    w_start = cfg.get("no_entries_before", DEFAULTS["no_entries_before"])
    w_end = getattr(args, "window_end", None) or cfg.get("no_entries_after", DEFAULTS["no_entries_after"])

    res = evaluate_entry(
        symbol=args.symbol,
        bars=bars,
        setup=args.setup,
        level=args.level,
        or_minutes=args.or_minutes,
        min_vol_x=args.min_volume_x,
        rvol_mult=args.rvol_mult,
        min_or_width_pct=args.min_or_width,
        max_or_width_pct=args.max_or_width,
        min_close_pos=args.min_close_pos,
        max_upper_wick=args.max_upper_wick,
        require_vwap=args.require_vwap,
        window_start=w_start,
        window_end=w_end,
        direction=getattr(args, "direction", "long"),
    )

    if args.write or res.get("status") == "triggered":
        if not args.no_write and res.get("status") == "triggered":
            os.makedirs("trader", exist_ok=True)
            with open("trader/entry.json", "w", encoding="utf-8") as fh:
                json.dump(res, fh, indent=2)

    if args.json:
        print(json.dumps(res, indent=2))
    else:
        st = res["status"].upper()
        if st == "TRIGGERED":
            vwap_txt = " (VWAP ₹%.2f, RVol %.1fx)" % (res["vwap"], res["rvol"]) if res.get("vwap") else ""
            side_txt = " [%s]" % res.get("side", "BUY").upper()
            pct_txt = "+%.2f%% over" % res["pct_over"] if "pct_over" in res else "-%.2f%% under" % res.get("pct_under", 0.0)
            lvl_txt = res.get("or_high") if res.get("side") == "buy" else res.get("or_low", res.get("level"))
            print("%s%s %s @ ₹%.2f at %s%s (%s ₹%.2f)" % (
                st, side_txt, res["symbol"], res["entry_price"], res["trigger_time"],
                vwap_txt, pct_txt, lvl_txt
            ))
        else:
            print("%s %s: %s" % (st, clean_symbol(args.symbol), res.get("reason", "")))

    return 0 if res["status"] == "triggered" else 1


def run_watch(args):
    print("Watching %s bar by bar (every %ds, until %s IST)..." % (
        clean_symbol(args.symbol), args.every, args.until or DEFAULTS["no_entries_after"]
    ))
    while True:
        now_utc = parse_now(args.now)
        chart = fetch_chart(args.symbol, interval="5m", offline=args.offline)
        bars = parse_bars(chart, interval_sec=300, cutoff_utc=now_utc)
        res = evaluate_entry(
            symbol=args.symbol,
            bars=bars,
            setup=args.setup,
            level=args.level,
            or_minutes=args.or_minutes,
            min_vol_x=args.min_volume_x,
            rvol_mult=args.rvol_mult,
            min_or_width_pct=args.min_or_width,
            max_or_width_pct=args.max_or_width,
            min_close_pos=args.min_close_pos,
            max_upper_wick=args.max_upper_wick,
            require_vwap=args.require_vwap,
            window_end=args.until or DEFAULTS["no_entries_after"],
            direction=getattr(args, "direction", "long"),
        )

        last_time = bars[-1]["ist_time"] if bars else "--:--"
        last_close = bars[-1]["close"] if bars else 0.0

        if res["status"] == "triggered":
            print("TRIGGERED: %s %s @ ₹%.2f at %s" % (
                res.get("side", "BUY").upper(), res["symbol"], res["entry_price"], res["trigger_time"]
            ))
            os.makedirs("trader", exist_ok=True)
            with open("trader/entry.json", "w", encoding="utf-8") as fh:
                json.dump(res, fh, indent=2)
            return 0
        elif res["status"] == "expired":
            print("EXPIRED: %s cutoff reached" % res["symbol"])
            return 1

        print("  [%s IST] bar closed @ ₹%.2f: %s" % (last_time, last_close, res.get("reason", "waiting")))
        if args.now or args.offline:
            break
        time.sleep(args.every)

    return 1


def run_watchlist(args):
    if not os.path.isfile("trader/watchlist.json"):
        print("error: trader/watchlist.json not found", file=sys.stderr)
        return 1
    with open("trader/watchlist.json", encoding="utf-8") as fh:
        wl = json.load(fh)
    hits = wl.get("hits", [])
    if not hits:
        print("Watchlist has no hits.")
        return 1

    triggered = []
    for h in hits:
        sym = clean_symbol(h.get("symbol"))
        try:
            chart = fetch_chart(sym, interval="5m", offline=args.offline)
            bars = parse_bars(chart, interval_sec=300, cutoff_utc=parse_now(args.now))
            res = evaluate_entry(
                sym, bars, setup="orb", or_minutes=15,
                min_or_width_pct=args.min_or_width,
                max_or_width_pct=args.max_or_width,
                min_close_pos=args.min_close_pos,
                max_upper_wick=args.max_upper_wick,
                require_vwap=args.require_vwap,
                rvol_mult=args.rvol_mult,
                window_end=args.window_end or DEFAULTS["no_entries_after"],
                direction=getattr(args, "direction", "long"),
            )
            if res.get("status") == "triggered":
                triggered.append(res)
                print("TRIGGERED: %-4s %-10s @ ₹%.2f at %s" % (
                    res.get("side", "BUY").upper(), sym, res["entry_price"], res["trigger_time"]
                ))
            else:
                print("WAITING:   %-10s %s" % (sym, res.get("reason", "")))
        except Exception as e:
            print("ERROR:     %-10s %s" % (sym, e))

    if triggered and not args.no_write:
        with open("trader/entry.json", "w", encoding="utf-8") as fh:
            json.dump(triggered[0], fh, indent=2)

    return 0 if triggered else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description="Entry Timer for Indian Stocks.")
    sub = parser.add_subparsers(dest="subcommand", required=True)

    # check
    p_c = sub.add_parser("check", help="Check if setup has triggered")
    p_c.add_argument("symbol", help="Stock ticker (e.g. RELIANCE)")
    p_c.add_argument("--setup", default="orb", choices=["orb", "level"], help="Setup rule")
    p_c.add_argument("--direction", default="long", choices=["long", "short", "both"], help="Breakout trade direction (long, short, or both)")
    p_c.add_argument("--level", type=float, help="Breakout level price (for level setup)")
    p_c.add_argument("--or-minutes", type=int, default=15, help="Opening range duration in minutes")
    p_c.add_argument("--interval", default="5m", choices=["1m", "5m"], help="Bar interval")
    p_c.add_argument("--min-volume-x", type=float, default=1.0, help="Volume confirmation multiplier vs OR average")
    p_c.add_argument("--rvol-mult", type=float, default=1.0, help="Volume surge multiplier vs 5-bar rolling average")
    p_c.add_argument("--min-or-width", type=float, default=0.4, help="Minimum opening range width in %% (default 0.4%%)")
    p_c.add_argument("--max-or-width", type=float, default=2.0, help="Maximum opening range width in %% (default 2.0%%)")
    p_c.add_argument("--min-close-pos", type=float, default=0.65, help="Minimum candle close position (0.0 to 1.0, default 0.65)")
    p_c.add_argument("--max-upper-wick", type=float, default=0.35, help="Maximum candle upper wick fraction (default 0.35)")
    p_c.add_argument("--window-end", default=None, help="Stop entries at this IST time (default 10:15)")
    p_c.add_argument("--require-vwap", dest="require_vwap", action="store_true", default=True, help="Require price > intraday VWAP")
    p_c.add_argument("--no-vwap", dest="require_vwap", action="store_false", help="Disable VWAP filter")
    p_c.add_argument("--now", help="Simulate clock (YYYY-MM-DD HH:MM IST)")
    p_c.add_argument("--offline", help="Path to offline JSON chart")
    p_c.add_argument("--write", action="store_true", help="Write trader/entry.json on trigger")
    p_c.add_argument("--no-write", action="store_true", help="Do not write trader/entry.json")
    p_c.add_argument("--json", action="store_true", help="Output JSON only")

    # watch
    p_w = sub.add_parser("watch", help="Poll bar by bar until trigger")
    p_w.add_argument("symbol", help="Stock ticker")
    p_w.add_argument("--setup", default="orb", choices=["orb", "level"])
    p_w.add_argument("--direction", default="long", choices=["long", "short", "both"])
    p_w.add_argument("--level", type=float)
    p_w.add_argument("--or-minutes", type=int, default=15)
    p_w.add_argument("--min-volume-x", type=float, default=1.0)
    p_w.add_argument("--rvol-mult", type=float, default=1.0)
    p_w.add_argument("--min-or-width", type=float, default=0.4)
    p_w.add_argument("--max-or-width", type=float, default=2.0)
    p_w.add_argument("--min-close-pos", type=float, default=0.65)
    p_w.add_argument("--max-upper-wick", type=float, default=0.35)
    p_w.add_argument("--require-vwap", dest="require_vwap", action="store_true", default=True)
    p_w.add_argument("--no-vwap", dest="require_vwap", action="store_false")
    p_w.add_argument("--every", type=int, default=30, help="Seconds between polls")
    p_w.add_argument("--until", default="10:15", help="Stop polling at this IST time (default 10:15)")
    p_w.add_argument("--now", help="Simulate clock")
    p_w.add_argument("--offline", help="Path to offline chart")

    # watchlist
    p_wl = sub.add_parser("watchlist", help="Check all symbols in trader/watchlist.json")
    p_wl.add_argument("--direction", default="long", choices=["long", "short", "both"])
    p_wl.add_argument("--min-or-width", type=float, default=0.4)
    p_wl.add_argument("--max-or-width", type=float, default=2.0)
    p_wl.add_argument("--rvol-mult", type=float, default=1.0)
    p_wl.add_argument("--min-close-pos", type=float, default=0.65)
    p_wl.add_argument("--max-upper-wick", type=float, default=0.35)
    p_wl.add_argument("--window-end", default=None)
    p_wl.add_argument("--require-vwap", dest="require_vwap", action="store_true", default=True)
    p_wl.add_argument("--no-vwap", dest="require_vwap", action="store_false")
    p_wl.add_argument("--now", help="Simulate clock")
    p_wl.add_argument("--offline", help="Path to offline directory")
    p_wl.add_argument("--no-write", action="store_true")

    args = parser.parse_args(argv)
    try:
        if args.subcommand == "check":
            return run_check(args)
        elif args.subcommand == "watch":
            return run_watch(args)
        elif args.subcommand == "watchlist":
            return run_watchlist(args)
    except EntryError as err:
        print("error: %s" % err, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
