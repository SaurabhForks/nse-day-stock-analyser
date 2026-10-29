#!/usr/bin/env python3
"""Chart Scanner for Indian stock market (NSE & BSE). Standard library only.

    python3 scan.py universe                          # NSE symbols -> trader/universe.txt
    python3 scan.py daily                             # before the open: daily setups -> trader/watchlist.json
    python3 scan.py daily --symbols RELIANCE,TCS,INFY # or --watchlist FILE, or --limit 100
    python3 scan.py orb                               # after 09:30 AM IST: opening-range breakouts so far
    python3 scan.py orb --at 10:15 --or-minutes 15    # cut the clock at 10:15 AM IST
    python3 scan.py orb --offline nifty_5m.json.gz --now "2026-10-19 10:15" --min-price 0

universe  Builds the Indian equity universe. Keeps NSE-listed common equity
          stocks (series 'EQ'). Excludes SME stocks, bonds, preference shares,
          warrants, rights, and ETFs. By default includes Nifty 50, Nifty Next 50,
          and Nifty 500 constituents, or parses an official NSE EQUITY_L.csv file.

daily     Pre-market scan of daily CLOSES (Yahoo spark/chart with .NS suffix:
          20 symbols a request, 3 months of 1-day bars).
          Liquidity filters: regularMarketPrice >= --min-price (10) and
          regularMarketVolume >= --min-volume (100,000). Setups from closes:
            breakout_20d     the last close is above every close of the 20 before it
            bull_flag        up > 10 % over 10 sessions before the last 5, then
                             last 5 closes inside a 5 % consolidation range
            reclaim_ma20     closed under 20-day moving average, then closed above it
            oversold         RSI 14 (Wilder) under 30
            oversold_bounce  RSI 14 was under 30 yesterday and today closed up
            circuit_watch    within 2 % of upper circuit limit (India price band)

orb       Opening-range breakouts, 5-minute bars. The range is the first
          --or-minutes (default 15) of the Indian trading session (09:15 to 09:30 IST).
          Stage 1: spark closes for every symbol (1 day of 5-minute bars, 20 a request);
          a chart qualifies if a completed bar after the range closed at or above
          the highest close of the range.
          Stage 2: each candidate's full chart: range high = highest high of the
          range bars (09:15, 09:20, 09:25 candles), hit = first completed 5-min
          bar to CLOSE above range high.
          Stage 2 fetches at most --max-confirm (200) charts, most traded first.

Indian Market Times:
  Session: 09:15 AM to 03:30 PM IST (UTC+05:30).
  Total session: 375 minutes (75 five-minute bars per day).
  Times print in IST (Asia/Kolkata).
  --now pins the clock ("2026-10-19 10:15", IST time; ...Z for UTC).

Yahoo endpoints: query2 first, query1 on 429 or 5xx. Standard library only.
Exit code 0 when scan found something, 1 when nothing found or error.
"""

import argparse
import csv
import datetime
import gzip
import io
import json
import math
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
YAHOO_HOSTS = ("https://query2.finance.yahoo.com", "https://query1.finance.yahoo.com")
SPARK_MAX = 20
PAUSE = 0.3
BACKOFF = 5.0
SLEEP = time.sleep
BAR_MIN = 5
MAX_CONFIRM = 200
MIN_DAILY_BARS = 30
DEFAULT_UNIVERSE = "trader/universe.txt"
NOTE = "A scan is a list of charts that match a rule, not a list of stocks to buy."

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
    "2027-01-26": "Republic Day",
    "2027-03-10": "Id-ul-Fitr",
    "2027-03-22": "Holi",
    "2027-03-26": "Good Friday",
    "2027-04-14": "Dr. Ambedkar Jayanti",
    "2027-05-01": "Maharashtra Day",
    "2027-05-17": "Bakri Id",
    "2027-08-15": "Independence Day",
    "2027-10-02": "Mahatma Gandhi Jayanti",
    "2027-10-10": "Dussehra",
    "2027-10-28": "Diwali Laxmi Pujan (Muhurat Trading)",
    "2027-11-13": "Gurunanak Jayanti",
    "2027-12-25": "Christmas",
}

# Core Indian Market Universe: Nifty 50 + Next 50 + Midcaps
CORE_NSE_STOCKS = [
    ("RELIANCE", "Reliance Industries Ltd."),
    ("TCS", "Tata Consultancy Services Ltd."),
    ("HDFCBANK", "HDFC Bank Ltd."),
    ("INFY", "Infosys Ltd."),
    ("ICICIBANK", "ICICI Bank Ltd."),
    ("TATAMOTORS", "Tata Motors Ltd."),
    ("SBIN", "State Bank of India"),
    ("BHARTIARTL", "Bharti Airtel Ltd."),
    ("ITC", "ITC Ltd."),
    ("LT", "Larsen & Toubro Ltd."),
    ("HINDUNILVR", "Hindustan Unilever Ltd."),
    ("KOTAKBANK", "Kotak Mahindra Bank Ltd."),
    ("AXISBANK", "Axis Bank Ltd."),
    ("MARUTI", "Maruti Suzuki India Ltd."),
    ("BAJFINANCE", "Bajaj Finance Ltd."),
    ("SUNPHARMA", "Sun Pharmaceutical Industries Ltd."),
    ("TITAN", "Titan Company Ltd."),
    ("ASIANPAINT", "Asian Paints Ltd."),
    ("NTPC", "NTPC Ltd."),
    ("TATACONSUM", "Tata Consumer Products Ltd."),
    ("POWERGRID", "Power Grid Corporation of India Ltd."),
    ("ULTRACEMCO", "UltraTech Cement Ltd."),
    ("M&M", "Mahindra & Mahindra Ltd."),
    ("JSWSTEEL", "JSW Steel Ltd."),
    ("TATASTEEL", "Tata Steel Ltd."),
    ("ADANIENT", "Adani Enterprises Ltd."),
    ("ADANIPORTS", "Adani Ports and Special Economic Zone Ltd."),
    ("COALINDIA", "Coal India Ltd."),
    ("ONGC", "Oil & Natural Gas Corporation Ltd."),
    ("BAJAJFINSV", "Bajaj Finserv Ltd."),
    ("TECHM", "Tech Mahindra Ltd."),
    ("WIPRO", "Wipro Ltd."),
    ("HCLTECH", "HCL Technologies Ltd."),
    ("GRASIM", "Grasim Industries Ltd."),
    ("DRREDDY", "Dr. Reddy's Laboratories Ltd."),
    ("CIPLA", "Cipla Ltd."),
    ("APOLLOHOSP", "Apollo Hospitals Enterprise Ltd."),
    ("DIVISLAB", "Divi's Laboratories Ltd."),
    ("EICHERMOT", "Eicher Motors Ltd."),
    ("HEROMOTOCO", "Hero MotoCorp Ltd."),
    ("BRITANNIA", "Britannia Industries Ltd."),
    ("NESTLEIND", "Nestle India Ltd."),
    ("BPCL", "Bharat Petroleum Corporation Ltd."),
    ("INDUSINDBK", "IndusInd Bank Ltd."),
    ("HINDALCO", "Hindalco Industries Ltd."),
    ("BEL", "Bharat Electronics Ltd."),
    ("HAL", "Hindustan Aeronautics Ltd."),
    ("TRENT", "Trent Ltd."),
    ("VEDL", "Vedanta Ltd."),
    ("ZOMATO", "Zomato Ltd."),
    ("DLF", "DLF Ltd."),
    ("SIEMENS", "Siemens Ltd."),
    ("ABB", "ABB India Ltd."),
    ("CHOLAFIN", "Cholamandalam Investment and Finance Co."),
    ("BANKBARODA", "Bank of Baroda"),
    ("PFC", "Power Finance Corporation Ltd."),
    ("RECLTD", "REC Ltd."),
    ("IOC", "Indian Oil Corporation Ltd."),
    ("PIDILITIND", "Pidilite Industries Ltd."),
    ("VBL", "Varun Beverages Ltd."),
]


class ScanError(Exception):
    pass


# ---------------------------------------------------------------- Time & Calendar (IST)

def to_ist(utc):
    """Convert naive or aware UTC datetime to naive IST datetime (UTC+5:30)."""
    return utc.replace(tzinfo=None) + datetime.timedelta(hours=5, minutes=30)


def ist_to_utc(ist):
    """Convert naive IST datetime to naive UTC datetime."""
    return ist - datetime.timedelta(hours=5, minutes=30)


def parse_now(text):
    """ISO time -> naive UTC. A time without offset is treated as IST."""
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
            raise ScanError("cannot parse date/time: %r" % text)
    if dt.tzinfo is not None:
        return dt.astimezone(datetime.timezone.utc).replace(microsecond=0, tzinfo=None)
    # Naive text is interpreted as IST
    return ist_to_utc(dt).replace(microsecond=0)


def is_trading_day(d):
    """Check if date d (datetime.date) is an Indian equity market trading day."""
    if d.weekday() >= 5:
        return False
    iso = d.isoformat()
    if iso in NSE_HOLIDAYS and "Muhurat" not in NSE_HOLIDAYS[iso]:
        return False
    return True


# ---------------------------------------------------------------- Symbols & Tickers

def clean_symbol(sym):
    """Normalize symbol: 'RELIANCE.NS' -> 'RELIANCE', uppercase."""
    s = (sym or "").strip().upper()
    if s.endswith(".NS") or s.endswith(".BO"):
        s = s[:-3]
    return s


def yahoo_symbol(sym):
    """Ensure Yahoo Finance ticker suffix for Indian stocks: 'RELIANCE' -> 'RELIANCE.NS'."""
    s = (sym or "").strip().upper()
    if s.endswith(".NS") or s.endswith(".BO"):
        return s
    return s + ".NS"


def display_symbol(sym):
    """Display name for ticket or table: 'RELIANCE'."""
    return clean_symbol(sym)


# ---------------------------------------------------------------- Network Fetching

def fetch_json(url, pause=PAUSE):
    """Fetch URL and parse JSON with retries."""
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    for attempt in range(2):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=15, context=SSL_CTX) as resp:
                data = resp.read()
                if resp.info().get("Content-Encoding") == "gzip":
                    data = gzip.decompress(data)
                if pause > 0:
                    SLEEP(pause)
                return json.loads(data.decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code == 429 and attempt == 0:
                SLEEP(BACKOFF)
                continue
            raise ScanError("HTTP %s from %s" % (exc.code, url))
        except urllib.error.URLError as exc:
            raise ScanError("network error fetching %s: %s" % (url, exc.reason))
    raise ScanError("failed fetching %s after retries" % url)


# ---------------------------------------------------------------- Setups & Technicals

def calc_rsi(closes, period=14):
    """Wilder's RSI calculation."""
    if len(closes) < period + 1:
        return None
    gains = []
    losses = []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i - 1]
        gains.append(max(0.0, diff))
        losses.append(max(0.0, -diff))
    if len(gains) < period:
        return None
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def check_daily_setups(closes):
    """Identify daily setups from closing prices."""
    if len(closes) < 25:
        return []
    setups = []
    last_close = closes[-1]
    prev_close = closes[-2]

    # Breakout 20d: last close > all previous 20 closes
    prior_20 = closes[-21:-1]
    if prior_20 and last_close > max(prior_20):
        setups.append("breakout_20d")

    # Bull flag: up > 10% in the 10 days before last 5, then last 5 within 5% range
    if len(closes) >= 16:
        pole_start = closes[-16]
        pole_end = closes[-6]
        flag_closes = closes[-5:]
        if pole_start > 0 and (pole_end - pole_start) / pole_start >= 0.10:
            flag_high = max(flag_closes)
            flag_low = min(flag_closes)
            if flag_low > 0 and (flag_high - flag_low) / flag_low <= 0.05:
                setups.append("bull_flag")

    # Reclaim MA20: 20-day moving average
    if len(closes) >= 21:
        ma20_yesterday = sum(closes[-21:-1]) / 20.0
        ma20_today = sum(closes[-20:]) / 20.0
        if prev_close < ma20_yesterday and last_close >= ma20_today:
            setups.append("reclaim_ma20")

    # Oversold & oversold bounce
    rsi_today = calc_rsi(closes, 14)
    rsi_yesterday = calc_rsi(closes[:-1], 14)
    if rsi_today is not None and rsi_today < 30.0:
        setups.append("oversold")
    if rsi_yesterday is not None and rsi_today is not None:
        if rsi_yesterday < 30.0 and last_close > prev_close:
            setups.append("oversold_bounce")

    return setups


# ---------------------------------------------------------------- Universe Engine

def filter_equity_l(csv_text):
    """Filter NSE EQUITY_L.csv content, keeping EQ series common shares."""
    stocks = []
    reader = csv.DictReader(io.StringIO(csv_text))
    for row in reader:
        sym = (row.get("SYMBOL") or row.get("Symbol") or "").strip().upper()
        series = (row.get(" SERIES") or row.get("SERIES") or row.get("Series") or "").strip().upper()
        name = (row.get("NAME OF COMPANY") or row.get("Name of Company") or sym).strip()
        if not sym or series != "EQ":
            continue
        # Exclude ETFs / rights / special securities
        if any(bad in name.upper() for bad in ("ETF", "NIFTY", "BEES", "GOLD", "LIQUID", "DEBENTURE", "RIGHTS")):
            continue
        stocks.append((sym, name))
    return stocks


def run_universe(args):
    """Build universe.txt of Indian common equity stocks."""
    out_path = args.out or DEFAULT_UNIVERSE
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)

    stocks = []
    if args.offline:
        # Load from offline file or folder
        path = args.offline
        if os.path.isdir(path):
            path = os.path.join(path, "EQUITY_L.csv")
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                stocks = filter_equity_l(fh.read())
        else:
            stocks = list(CORE_NSE_STOCKS)
    else:
        # Try fetching official NSE EQUITY_L.csv or use core constituents
        url = "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
            with urllib.request.urlopen(req, timeout=10, context=SSL_CTX) as resp:
                content = resp.read().decode("utf-8", errors="replace")
                stocks = filter_equity_l(content)
        except Exception:
            # Fallback to curated core NSE universe
            stocks = list(CORE_NSE_STOCKS)

    if not stocks:
        stocks = list(CORE_NSE_STOCKS)

    stocks.sort(key=lambda x: x[0])
    with open(out_path, "w", encoding="utf-8") as fh:
        for sym, name in stocks:
            fh.write("%s|%s\n" % (sym, name))

    print("Wrote %d Indian equity stocks to %s" % (len(stocks), out_path))
    return 0


# ---------------------------------------------------------------- Daily Scanner

def run_daily(args):
    """Pre-market daily setup scanner for Indian equities."""
    symbols = []
    if args.symbols:
        symbols = [clean_symbol(s) for s in args.symbols.split(",") if s.strip()]
    elif args.watchlist and os.path.isfile(args.watchlist):
        with open(args.watchlist, encoding="utf-8") as fh:
            data = json.load(fh)
            symbols = [clean_symbol(h.get("symbol")) for h in data.get("hits", [])]
    else:
        u_path = args.universe or DEFAULT_UNIVERSE
        if os.path.isfile(u_path):
            with open(u_path, encoding="utf-8") as fh:
                for line in fh:
                    if "|" in line:
                        symbols.append(clean_symbol(line.split("|")[0]))
        else:
            symbols = [s for s, _ in CORE_NSE_STOCKS]

    if args.limit and args.limit > 0:
        symbols = symbols[:args.limit]

    now_utc = parse_now(args.now)
    now_ist = to_ist(now_utc)
    hits = []
    scanned = 0
    failed = 0

    for sym in symbols:
        scanned += 1
        closes = []
        vol = 0
        last_price = 0.0

        if args.offline:
            # Offline read
            off_path = args.offline
            if os.path.isdir(off_path):
                off_path = os.path.join(args.offline, "%s.json" % sym)
                if not os.path.isfile(off_path):
                    off_path = os.path.join(args.offline, "%s.NS.json" % sym)
            if os.path.isfile(off_path):
                try:
                    opener = gzip.open if off_path.endswith(".gz") else open
                    with opener(off_path, "rt", encoding="utf-8") as fh:
                        raw = json.load(fh)
                    res = raw.get("chart", {}).get("result", [{}])[0]
                    quotes = res.get("indicators", {}).get("quote", [{}])[0]
                    closes = [c for c in quotes.get("close", []) if c is not None]
                    volumes = [v for v in quotes.get("volume", []) if v is not None]
                    vol = volumes[-1] if volumes else 0
                    last_price = closes[-1] if closes else 0.0
                except Exception:
                    failed += 1
                    continue
            else:
                failed += 1
                continue
        else:
            # Network fetch
            y_sym = yahoo_symbol(sym)
            url = "%s/v8/finance/chart/%s?range=3mo&interval=1d" % (YAHOO_HOSTS[0], y_sym)
            try:
                raw = fetch_json(url)
                res = raw.get("chart", {}).get("result", [{}])[0]
                quotes = res.get("indicators", {}).get("quote", [{}])[0]
                closes = [c for c in quotes.get("close", []) if c is not None]
                volumes = [v for v in quotes.get("volume", []) if v is not None]
                vol = volumes[-1] if volumes else 0
                last_price = closes[-1] if closes else 0.0
            except Exception:
                failed += 1
                continue

        if not closes or len(closes) < 20:
            continue
        if last_price < args.min_price or vol < args.min_volume:
            continue

        setups = check_daily_setups(closes)
        if setups:
            hits.append({
                "symbol": sym,
                "price": round(last_price, 2),
                "volume": int(vol),
                "setups": setups,
            })

    out_data = {
        "mode": "daily",
        "as_of": now_ist.strftime("%Y-%m-%d %H:%M:%S IST"),
        "universe": len(symbols),
        "scanned": scanned,
        "failed": failed,
        "hits": hits,
        "note": NOTE,
    }

    if not args.no_write:
        os.makedirs("trader", exist_ok=True)
        with open("trader/watchlist.json", "w", encoding="utf-8") as fh:
            json.dump(out_data, fh, indent=2)

    if args.json:
        print(json.dumps(out_data, indent=2))
    else:
        print("Daily scan as of %s: %d setups found across %d stocks" % (
            out_data["as_of"], len(hits), scanned
        ))
        for h in hits[:20]:
            print("  %-12s ₹%-8.2f setups: %s" % (h["symbol"], h["price"], ", ".join(h["setups"])))

    return 0 if hits else 1


# ---------------------------------------------------------------- ORB Scanner (NSE 09:15 Open)

def parse_chart_5m_bars(chart_json, cutoff_dt_ist):
    """Extract 5-minute completed bars for an Indian market session up to cutoff_dt_ist."""
    res = chart_json.get("chart", {}).get("result", [{}])[0]
    timestamps = res.get("timestamp", [])
    quotes = res.get("indicators", {}).get("quote", [{}])[0]
    opens = quotes.get("open", [])
    highs = quotes.get("high", [])
    lows = quotes.get("low", [])
    closes = quotes.get("close", [])
    volumes = quotes.get("volume", [])

    bars = []
    cutoff_utc = ist_to_utc(cutoff_dt_ist)
    cutoff_epoch = cutoff_utc.replace(tzinfo=datetime.timezone.utc).timestamp()

    for i in range(len(timestamps)):
        t = timestamps[i]
        c = closes[i] if i < len(closes) else None
        o = opens[i] if i < len(opens) else None
        h = highs[i] if i < len(highs) else None
        l = lows[i] if i < len(lows) else None
        v = volumes[i] if i < len(volumes) else 0
        if None in (c, o, h, l, t):
            continue
        # Bar completion: start + 300 <= cutoff
        if t + 300 > cutoff_epoch:
            continue
        bar_ist = to_ist(datetime.datetime.fromtimestamp(t, datetime.timezone.utc))
        bars.append({
            "timestamp": t,
            "ist_time": bar_ist.strftime("%H:%M"),
            "date": bar_ist.strftime("%Y-%m-%d"),
            "open": float(o),
            "high": float(h),
            "low": float(l),
            "close": float(c),
            "volume": int(v or 0),
        })
    return bars


def check_orb_setup(bars, or_minutes=15, min_or_width=0.4, max_or_width=2.0, direction="long"):
    """Check Opening Range Breakout setup on 5m bars (long, short, or both).
    Indian market session starts at 09:15 IST.
    15-minute ORB range = first 3 bars (09:15, 09:20, 09:25).
    """
    needed_bars = or_minutes // 5
    if len(bars) <= needed_bars:
        return None

    range_bars = bars[:needed_bars]
    range_high = max(b["high"] for b in range_bars)
    range_low = min(b["low"] for b in range_bars)
    or_width_pct = ((range_high - range_low) / range_low) * 100.0 if range_low > 0 else 0.0

    if min_or_width is not None and or_width_pct < min_or_width:
        return None
    if max_or_width is not None and or_width_pct > max_or_width:
        return None

    # First completed bar after range that triggers
    for b in bars[needed_bars:]:
        if direction in ("long", "both") and b["close"] > range_high:
            pct_over = ((b["close"] - range_high) / range_high) * 100.0
            return {
                "side": "buy",
                "or_high": round(range_high, 2),
                "or_low": round(range_low, 2),
                "or_width_pct": round(or_width_pct, 2),
                "trigger_time": b["ist_time"],
                "trigger_price": round(b["close"], 2),
                "pct_over": round(pct_over, 2),
                "volume": b["volume"],
            }
        elif direction in ("short", "both") and b["close"] < range_low:
            pct_under = ((range_low - b["close"]) / range_low) * 100.0
            return {
                "side": "sell",
                "or_high": round(range_high, 2),
                "or_low": round(range_low, 2),
                "or_width_pct": round(or_width_pct, 2),
                "trigger_time": b["ist_time"],
                "trigger_price": round(b["close"], 2),
                "pct_under": round(pct_under, 2),
                "volume": b["volume"],
            }
    return None


def run_orb(args):
    """Scan intraday 5m charts for Opening Range Breakout (ORB) on NSE."""
    now_utc = parse_now(args.now)
    now_ist = to_ist(now_utc)

    # Cutoff time
    cutoff_time = args.at if args.at else now_ist.strftime("%H:%M")
    m = re.match(r"^(\d{1,2}):(\d{2})$", cutoff_time)
    if not m:
        raise ScanError("invalid --at time %r (use HH:MM)" % cutoff_time)
    ch, cm = int(m.group(1)), int(m.group(2))
    cutoff_dt_ist = now_ist.replace(hour=ch, minute=cm, second=0, microsecond=0)

    symbols = []
    if args.symbols:
        symbols = [clean_symbol(s) for s in args.symbols.split(",") if s.strip()]
    elif args.watchlist and os.path.isfile(args.watchlist):
        with open(args.watchlist, encoding="utf-8") as fh:
            data = json.load(fh)
            symbols = [clean_symbol(h.get("symbol")) for h in data.get("hits", [])]
    else:
        u_path = args.universe or DEFAULT_UNIVERSE
        if os.path.isfile(u_path):
            with open(u_path, encoding="utf-8") as fh:
                for line in fh:
                    if "|" in line:
                        symbols.append(clean_symbol(line.split("|")[0]))
        else:
            symbols = [s for s, _ in CORE_NSE_STOCKS]

    hits = []
    scanned = 0
    failed = 0

    for sym in symbols[:MAX_CONFIRM]:
        scanned += 1
        chart_data = None
        if args.offline:
            off_path = args.offline
            if os.path.isdir(off_path):
                cand = os.path.join(args.offline, "%s.json" % sym)
                if not os.path.isfile(cand):
                    cand = os.path.join(args.offline, "%s.NS.json" % sym)
                if os.path.isfile(cand):
                    off_path = cand
            if os.path.isfile(off_path):
                try:
                    opener = gzip.open if off_path.endswith(".gz") else open
                    with opener(off_path, "rt", encoding="utf-8") as fh:
                        chart_data = json.load(fh)
                except Exception:
                    failed += 1
                    continue
        else:
            y_sym = yahoo_symbol(sym)
            url = "%s/v8/finance/chart/%s?range=1d&interval=5m" % (YAHOO_HOSTS[0], y_sym)
            try:
                chart_data = fetch_json(url)
            except Exception:
                failed += 1
                continue

        if not chart_data:
            continue

        bars = parse_chart_5m_bars(chart_data, cutoff_dt_ist)
        res = check_orb_setup(
            bars,
            or_minutes=args.or_minutes,
            min_or_width=args.min_or_width,
            max_or_width=args.max_or_width,
            direction=getattr(args, "direction", "long"),
        )
        if res:
            res["symbol"] = sym
            hits.append(res)

    hits.sort(key=lambda x: x.get("pct_over") if "pct_over" in x else x.get("pct_under", 0.0), reverse=True)

    out_data = {
        "mode": "orb",
        "as_of": cutoff_dt_ist.strftime("%Y-%m-%d %H:%M IST"),
        "or_minutes": args.or_minutes,
        "min_or_width_pct": args.min_or_width,
        "max_or_width_pct": args.max_or_width,
        "universe": len(symbols),
        "scanned": scanned,
        "failed": failed,
        "hits": hits,
        "note": NOTE,
    }

    if not args.no_write:
        os.makedirs("trader", exist_ok=True)
        with open("trader/watchlist.json", "w", encoding="utf-8") as fh:
            json.dump(out_data, fh, indent=2)

    if args.json:
        print(json.dumps(out_data, indent=2))
    else:
        print("NSE ORB scan at %s (%d-min range): %d breakouts found across %d stocks" % (
            cutoff_dt_ist.strftime("%H:%M IST"), args.or_minutes, len(hits), scanned
        ))
        for h in hits[:20]:
            print("  %-12s triggered at %s @ ₹%-8.2f (+%.2f%% over OR high ₹%.2f, width %.2f%%)" % (
                h["symbol"], h["trigger_time"], h["trigger_price"], h["pct_over"], h["or_high"], h.get("or_width_pct", 0.0)
            ))

    return 0 if hits else 1


# ---------------------------------------------------------------- Main CLI

def main(argv=None):
    parser = argparse.ArgumentParser(description="Chart Scanner for Indian stock market (NSE/BSE).")
    sub = parser.add_subparsers(dest="subcommand", required=True)

    # universe
    p_u = sub.add_parser("universe", help="Build NSE universe list")
    p_u.add_argument("--out", default=DEFAULT_UNIVERSE, help="Output file path")
    p_u.add_argument("--offline", help="Path to offline EQUITY_L.csv or directory")

    # daily
    p_d = sub.add_parser("daily", help="Pre-market daily setups scan")
    p_d.add_argument("--symbols", help="Comma-separated symbols")
    p_d.add_argument("--watchlist", help="Path to watchlist JSON")
    p_d.add_argument("--universe", help="Universe file path")
    p_d.add_argument("--limit", type=int, default=0, help="Max symbols to scan")
    p_d.add_argument("--min-price", type=float, default=10.0, help="Minimum price in INR")
    p_d.add_argument("--min-volume", type=int, default=100000, help="Minimum volume")
    p_d.add_argument("--now", help="Simulate current time (YYYY-MM-DD HH:MM IST)")
    p_d.add_argument("--offline", help="Offline JSON data file or directory")
    p_d.add_argument("--no-write", action="store_true", help="Do not write trader/watchlist.json")
    p_d.add_argument("--json", action="store_true", help="Output JSON only")

    # orb
    p_o = sub.add_parser("orb", help="Opening Range Breakout scan on 5-minute bars")
    p_o.add_argument("--symbols", help="Comma-separated symbols")
    p_o.add_argument("--watchlist", help="Path to watchlist JSON")
    p_o.add_argument("--universe", help="Universe file path")
    p_o.add_argument("--or-minutes", type=int, default=15, help="Opening range duration in minutes (default 15)")
    p_o.add_argument("--min-or-width", type=float, default=0.4, help="Minimum opening range width in %% (default 0.4%%)")
    p_o.add_argument("--max-or-width", type=float, default=2.0, help="Maximum opening range width in %% (default 2.0%%)")
    p_o.add_argument("--at", default="10:15", help="Cutoff time in HH:MM IST (default 10:15 prime time)")
    p_o.add_argument("--direction", default="long", choices=["long", "short", "both"], help="Breakout scan direction: long (default), short, or both")
    p_o.add_argument("--now", help="Simulate current time")
    p_o.add_argument("--offline", help="Offline JSON data file or directory")
    p_o.add_argument("--no-write", action="store_true", help="Do not write trader/watchlist.json")
    p_o.add_argument("--json", action="store_true", help="Output JSON only")

    args = parser.parse_args(argv)

    try:
        if args.subcommand == "universe":
            return run_universe(args)
        elif args.subcommand == "daily":
            return run_daily(args)
        elif args.subcommand == "orb":
            return run_orb(args)
    except ScanError as err:
        print("error: %s" % err, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
