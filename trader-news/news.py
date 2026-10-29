#!/usr/bin/env python3
"""News & Corporate Actions Monitor for Indian Equities (NSE/BSE). Standard library only.

    python3 news.py                                  # watchlist + plan + portfolio tickers
    python3 news.py --tickers RELIANCE TCS INFY
    python3 news.py --tickers TATAMOTORS --hours 72  # last 3 days
    python3 news.py --no-moves                       # skip price change calculation

Watches breaking news, corporate announcements, earnings releases, and SEBI filings
for Indian equities. Formats times in IST (UTC+05:30). Remembers seen headlines
in trader/state/news.json to avoid repeating alerts.
"""

import argparse
import datetime as _dt
import email.utils
import gzip
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

YAHOO_RSS = "https://feeds.finance.yahoo.com/rss/2.0/headline?s=%s&region=IN&lang=en-IN"
CHART_URL = "https://%s.finance.yahoo.com/v8/finance/chart/%s?range=1d&interval=5m"
UA = "Mozilla/5.0 (compatible; indian-day-trader-skill/2.0; +https://github.com/SaurabhTomar/indian-day-trader-skill)"
KEEP_DAYS = 30
MOVE_PCT = 3.0

KEYWORDS = [
    ("results", r"\b(?:earnings|results|q[1-4]|profit|revenue|pat|ebitda|quarterly)\b"),
    ("corporate_action", r"\b(?:dividend|bonus|split|buyback|rights issue)\b"),
    ("orders", r"\b(?:order|contract|bagged|awarded|deal|tender|epc|railway|defence)\b"),
    ("regulatory", r"\b(?:sebi|probe|investigation|penalty|notice|it dept|enforcement|nclt|court)\b"),
    ("promoter_deal", r"\b(?:promoter|stake|block deal|bulk deal|pledge|unpledge|open offer|takeover)\b"),
    ("management", r"\b(?:ceo|cfo|managing director|md|resigned|resignation|appointed|auditor)\b"),
    ("circuit_halt", r"\b(?:circuit|upper circuit|lower circuit|trading halt|suspended)\b"),
    ("macro", r"\b(?:rbi|monetary policy|repo rate|inflation|cpi|crude|rupee|fii|dii)\b"),
]


class NewsError(Exception):
    pass


def to_ist(utc):
    """Convert naive or aware UTC datetime to naive IST datetime (UTC+5:30)."""
    return utc.replace(tzinfo=None) + _dt.timedelta(hours=5, minutes=30)


def ist_to_utc(ist):
    """Convert naive IST datetime to naive UTC datetime."""
    return ist - _dt.timedelta(hours=5, minutes=30)


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


def parse_rfc822(text):
    """Parse RSS date string into UTC datetime."""
    try:
        parsed = email.utils.parsedate_to_datetime(text)
        if parsed.tzinfo is not None:
            return parsed.astimezone(_dt.timezone.utc).replace(tzinfo=None)
        return parsed
    except Exception:
        return _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None)


def tag_headline(title):
    tags = []
    t_lower = title.lower()
    for cat, pat in KEYWORDS:
        if re.search(pat, t_lower):
            tags.append(cat)
    return tags


def fetch_url(url, timeout=10):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
            if resp.info().get("Content-Encoding") == "gzip":
                data = gzip.decompress(data)
            return data
    except urllib.error.HTTPError as exc:
        raise NewsError("HTTP %s for %s" % (exc.code, url))
    except urllib.error.URLError as exc:
        raise NewsError("could not reach %s: %s" % (url, exc.reason))


def parse_rss_items(xml_bytes, symbol):
    """Parse RSS XML into structured news items."""
    items = []
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return items

    channel = root.find("channel")
    if channel is None:
        return items

    for it in channel.findall("item"):
        title = (it.findtext("title") or "").strip()
        link = (it.findtext("link") or "").strip()
        pub_date = (it.findtext("pubDate") or "").strip()
        if not title:
            continue
        dt_utc = parse_rfc822(pub_date)
        dt_ist = to_ist(dt_utc)
        item_id = hashlib.sha1((link or title).encode("utf-8")).hexdigest()
        tags = tag_headline(title)
        items.append({
            "id": item_id,
            "symbol": clean_symbol(symbol),
            "title": title,
            "link": link,
            "time_utc": dt_utc.strftime("%Y-%m-%d %H:%M:%S"),
            "time_ist": dt_ist.strftime("%Y-%m-%d %H:%M:%S IST"),
            "published_at": dt_ist.strftime("%H:%M IST"),
            "date": dt_ist.strftime("%Y-%m-%d"),
            "tags": tags,
        })
    return items


def get_stock_move(sym, offline=None):
    """Fetch today's current price and move % compared to yesterday's close."""
    chart_data = None
    if offline:
        path = os.path.join(offline, "chart-%s.json" % sym)
        if not os.path.isfile(path):
            path = os.path.join(offline, "%s.json" % sym)
        if os.path.isfile(path):
            try:
                opener = gzip.open if path.endswith(".gz") else open
                with opener(path, "rt", encoding="utf-8") as fh:
                    chart_data = json.load(fh)
            except Exception:
                pass
    else:
        y_sym = yahoo_symbol(sym)
        url = CHART_URL % ("query2", y_sym)
        try:
            raw = fetch_url(url, timeout=5)
            chart_data = json.loads(raw.decode("utf-8"))
        except Exception:
            pass

    if not chart_data:
        return None

    try:
        res = chart_data.get("chart", {}).get("result", [{}])[0]
        meta = res.get("meta", {})
        price = meta.get("regularMarketPrice")
        prev = meta.get("chartPreviousClose") or meta.get("previousClose")
        if price is not None and prev and prev > 0:
            pct = ((price - prev) / prev) * 100.0
            return {
                "price": round(price, 2),
                "prev_close": round(prev, 2),
                "change_pct": round(pct, 2),
            }
    except Exception:
        pass
    return None


def run_news(args):
    symbols = []
    if args.tickers:
        symbols = [clean_symbol(s) for s in args.tickers]
    else:
        # Collect from files
        for f, key in (("trader/watchlist.json", "hits"), ("trader/plan.json", "symbol"),
                       ("trader/portfolio.json", "positions")):
            if os.path.isfile(f):
                try:
                    with open(f, encoding="utf-8") as fh:
                        data = json.load(fh)
                        if key == "hits":
                            symbols.extend(clean_symbol(h.get("symbol")) for h in data.get("hits", []))
                        elif key == "symbol" and data.get("symbol"):
                            symbols.append(clean_symbol(data["symbol"]))
                        elif key == "positions" and isinstance(data.get("positions"), list):
                            symbols.extend(clean_symbol(p.get("symbol")) for p in data.get("positions", []))
                except Exception:
                    pass

    symbols = sorted(list(dict.fromkeys(symbols)))
    if not symbols:
        symbols = ["RELIANCE", "TCS", "INFY"]

    # State file to track seen news
    state_file = "trader/state/news.json"
    seen_ids = set()
    if os.path.isfile(state_file):
        try:
            with open(state_file, encoding="utf-8") as fh:
                state_data = json.load(fh)
                seen_ids = set(state_data.get("seen", []))
        except Exception:
            pass

    cutoff_dt = _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None) - _dt.timedelta(hours=args.hours)
    all_items = []
    new_seen = set(seen_ids)

    for sym in symbols:
        items = []
        if args.offline:
            off_path = os.path.join(args.offline, "yahoo-%s.xml" % sym)
            if not os.path.isfile(off_path):
                off_path = os.path.join(args.offline, "%s.xml" % sym)
            if os.path.isfile(off_path):
                try:
                    with open(off_path, "rb") as fh:
                        items = parse_rss_items(fh.read(), sym)
                except Exception:
                    pass
        else:
            y_sym = yahoo_symbol(sym)
            url = YAHOO_RSS % y_sym
            try:
                xml_data = fetch_url(url)
                items = parse_rss_items(xml_data, sym)
            except Exception:
                pass

        # Filter by hours
        fresh = []
        for it in items:
            it_dt = _dt.datetime.strptime(it["time_utc"], "%Y-%m-%d %H:%M:%S")
            if it_dt >= cutoff_dt:
                fresh.append(it)
        all_items.extend(fresh)

    # Sort newest first
    all_items.sort(key=lambda x: x["time_utc"], reverse=True)

    unseen_items = []
    for it in all_items:
        if args.all or it["id"] not in seen_ids:
            unseen_items.append(it)
        new_seen.add(it["id"])

    # Update state file
    if not args.no_write:
        os.makedirs("trader/state", exist_ok=True)
        with open(state_file, "w", encoding="utf-8") as fh:
            json.dump({"seen": list(new_seen)[-5000:], "updated": _dt.datetime.now().isoformat()}, fh, indent=2)

    # Output
    if args.json:
        print(json.dumps(unseen_items, indent=2))
        return 0

    print("News & Corporate Actions Monitor (%d tickers, last %d hours):" % (len(symbols), args.hours))
    if not args.no_moves:
        moves = []
        for sym in symbols:
            m = get_stock_move(sym, offline=args.offline)
            if m:
                sign = "+" if m["change_pct"] >= 0 else ""
                flag = " [!] MOVING" if abs(m["change_pct"]) >= MOVE_PCT else ""
                moves.append("%s: ₹%.2f (%s%.2f%%%s)" % (sym, m["price"], sign, m["change_pct"], flag))
        if moves:
            print("Current moves: " + " | ".join(moves))
            print("-" * 60)

    if not unseen_items:
        print("No new headlines.")
        return 0

    for it in unseen_items:
        tag_str = (" [%s]" % ", ".join(it["tags"])) if it["tags"] else ""
        print("%s | %-10s %s%s" % (it["published_at"], it["symbol"], it["title"], tag_str))
        if it.get("link"):
            print("   -> %s" % it["link"])

    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="News & Corporate Actions Monitor for Indian Stocks.")
    parser.add_argument("--tickers", nargs="+", help="Symbols to monitor (e.g. RELIANCE TCS)")
    parser.add_argument("--hours", type=int, default=24, help="Lookback window in hours (default 24)")
    parser.add_argument("--all", action="store_true", help="Print all items, seen or not")
    parser.add_argument("--no-moves", action="store_true", help="Do not print today's stock price move")
    parser.add_argument("--offline", help="Path to offline folder with mock RSS XML and charts")
    parser.add_argument("--no-write", action="store_true", help="Do not save state")
    parser.add_argument("--json", action="store_true", help="Output JSON only")

    args = parser.parse_args(argv)
    try:
        return run_news(args)
    except NewsError as err:
        print("error: %s" % err, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
