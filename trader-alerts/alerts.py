#!/usr/bin/env python3
"""Price Alerts & NSE Clock for Indian Equities. Standard library only.

    python3 alerts.py clock                          # is the NSE open? next open/close
    python3 alerts.py quote RELIANCE --write         # quotes -> trader/prices.json
    python3 alerts.py quote --holdings --write       # every ticker in portfolio and plan
    python3 alerts.py add --from-plan                # stop, target, and flat-by from plan.json
    python3 alerts.py add --symbol RELIANCE --stop 2480.00
    python3 alerts.py add --symbol RELIANCE --target 2540.00
    python3 alerts.py add --at 15:15 --label "MIS square off"
    python3 alerts.py add --opening-bell
    python3 alerts.py check                          # rings what hit, once; exit 1 if quiet
    python3 alerts.py list
    python3 alerts.py reset reliance-stop
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
BACKOFF = 2.0
YAHOO_HOSTS = ("query2.finance.yahoo.com", "query1.finance.yahoo.com")
HHMM = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")

NSE_HOLIDAYS = {
    "2026-01-26": "Republic Day", "2026-03-03": "Holi", "2026-03-20": "Id-ul-Fitr",
    "2026-03-27": "Ram Navami", "2026-04-03": "Good Friday", "2026-04-14": "Dr. Ambedkar Jayanti",
    "2026-05-01": "Maharashtra Day", "2026-05-27": "Bakri Id", "2026-06-25": "Moharram",
    "2026-08-15": "Independence Day", "2026-10-02": "Mahatma Gandhi Jayanti", "2026-10-20": "Dussehra",
    "2026-11-08": "Diwali Laxmi Pujan", "2026-11-10": "Diwali Balipratipada",
    "2026-11-24": "Gurunanak Jayanti", "2026-12-25": "Christmas",
    "2027-01-26": "Republic Day", "2027-03-10": "Id-ul-Fitr", "2027-03-22": "Holi",
    "2027-03-26": "Good Friday", "2027-04-14": "Dr. Ambedkar Jayanti", "2027-05-01": "Maharashtra Day",
    "2027-05-17": "Bakri Id", "2027-08-15": "Independence Day", "2027-10-02": "Mahatma Gandhi Jayanti",
    "2027-10-10": "Dussehra", "2027-10-28": "Diwali Laxmi Pujan", "2027-11-13": "Gurunanak Jayanti",
    "2027-12-25": "Christmas",
}

OPEN_TIME = datetime.time(9, 15)
CLOSE_TIME = datetime.time(15, 30)
MIS_TIME = datetime.time(15, 15)


class AlertError(Exception):
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
            raise AlertError("cannot parse date/time: %r" % text)
    if dt.tzinfo is not None:
        return dt.astimezone(datetime.timezone.utc).replace(microsecond=0, tzinfo=None)
    return ist_to_utc(dt).replace(microsecond=0)


def fetch_quote(symbol, offline=None):
    sym = clean_symbol(symbol)
    if offline:
        path = offline
        if os.path.isdir(path):
            cand = os.path.join(path, "quote-%s.json" % sym)
            if not os.path.isfile(cand):
                cand = os.path.join(path, "%s.json" % sym)
            if not os.path.isfile(cand):
                cand = os.path.join(path, "%s.NS.json" % sym)
            if os.path.isfile(cand):
                path = cand
        if os.path.isfile(path):
            opener = gzip.open if path.endswith(".gz") else open
            with opener(path, "rt", encoding="utf-8") as fh:
                data = json.load(fh)
                res = data.get("chart", {}).get("result", [{}])[0]
                meta = res.get("meta", {})
                price = meta.get("regularMarketPrice")
                prev = meta.get("chartPreviousClose") or meta.get("previousClose")
                return {
                    "symbol": sym,
                    "price": float(price) if price else 0.0,
                    "prev_close": float(prev) if prev else 0.0,
                    "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S IST"),
                }
        raise AlertError("offline quote file not found: %s" % path)

    y_sym = yahoo_symbol(sym)
    url = "https://%s/v8/finance/chart/%s?range=1d&interval=5m" % (YAHOO_HOSTS[0], y_sym)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
    try:
        with urllib.request.urlopen(req, timeout=10, context=SSL_CTX) as resp:
            data = resp.read()
            if resp.info().get("Content-Encoding") == "gzip":
                data = gzip.decompress(data)
            parsed = json.loads(data.decode("utf-8"))
            res = parsed.get("chart", {}).get("result", [{}])[0]
            meta = res.get("meta", {})
            price = meta.get("regularMarketPrice")
            prev = meta.get("chartPreviousClose") or meta.get("previousClose")
            return {
                "symbol": sym,
                "price": float(price) if price else 0.0,
                "prev_close": float(prev) if prev else 0.0,
                "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S IST"),
            }
    except Exception as exc:
        raise AlertError("failed fetching quote for %s: %s" % (sym, exc))


def run_clock(args):
    now_utc = parse_now(args.now)
    now_ist = to_ist(now_utc)
    cur_date = now_ist.date()
    cur_time = now_ist.time()

    is_weekend = cur_date.weekday() >= 5
    d_iso = cur_date.isoformat()
    holiday_name = NSE_HOLIDAYS.get(d_iso)

    if is_weekend:
        status = "CLOSED (Weekend)"
    elif holiday_name:
        status = "CLOSED (Holiday: %s)" % holiday_name
    elif cur_time < OPEN_TIME:
        status = "PRE-MARKET (Opens at 09:15 AM IST)"
    elif cur_time >= CLOSE_TIME:
        status = "CLOSED (Regular market closed at 03:30 PM IST)"
    elif cur_time >= MIS_TIME:
        status = "OPEN - MIS AUTO-SQUARE-OFF WINDOW (03:15 to 03:30 PM IST)"
    else:
        status = "OPEN (Normal Trading Session)"

    res = {
        "clock_ist": now_ist.strftime("%Y-%m-%d %H:%M:%S IST"),
        "status": status,
        "is_open": ("OPEN" in status and "CLOSED" not in status),
        "is_trading_day": not (is_weekend or holiday_name),
    }

    if args.json:
        print(json.dumps(res, indent=2))
    else:
        print("NSE Market Clock: %s" % res["clock_ist"])
        print("Market Status:    %s" % res["status"])
    return 0


def run_quote(args):
    symbols = []
    if args.symbol:
        symbols.append(clean_symbol(args.symbol))
    elif args.holdings:
        # Load from portfolio and plan
        for f, key in (("trader/plan.json", "symbol"), ("trader/portfolio.json", "positions")):
            if os.path.isfile(f):
                try:
                    with open(f, encoding="utf-8") as fh:
                        data = json.load(fh)
                        if key == "symbol" and data.get("symbol"):
                            symbols.append(clean_symbol(data["symbol"]))
                        elif key == "positions" and isinstance(data.get("positions"), list):
                            symbols.extend(clean_symbol(p.get("symbol")) for p in data.get("positions", []))
                except Exception:
                    pass

    symbols = sorted(list(dict.fromkeys(symbols)))
    if not symbols:
        symbols = ["RELIANCE", "TCS", "INFY"]

    prices = {}
    if os.path.isfile("trader/prices.json"):
        try:
            with open("trader/prices.json", encoding="utf-8") as fh:
                prices = json.load(fh)
        except Exception:
            pass

    for sym in symbols:
        try:
            q = fetch_quote(sym, offline=args.offline)
            prices[sym] = q
            if not args.json:
                print("Quote: %-10s ₹%.2f (prev close ₹%.2f)" % (sym, q["price"], q["prev_close"]))
        except Exception as e:
            print("Quote error for %s: %s" % (sym, e), file=sys.stderr)

    if args.write or not args.no_write:
        os.makedirs("trader", exist_ok=True)
        with open("trader/prices.json", "w", encoding="utf-8") as fh:
            json.dump(prices, fh, indent=2)

    if args.json:
        print(json.dumps(prices, indent=2))
    return 0


def run_add(args):
    alerts_file = "trader/alerts.json"
    rules = []
    if os.path.isfile(alerts_file):
        try:
            with open(alerts_file, encoding="utf-8") as fh:
                rules = json.load(fh).get("rules", [])
        except Exception:
            pass

    new_rules = []
    if args.from_plan:
        if not os.path.isfile("trader/plan.json"):
            raise AlertError("trader/plan.json not found")
        with open("trader/plan.json", encoding="utf-8") as fh:
            p = json.load(fh)
        sym = clean_symbol(p["symbol"])
        date_str = p.get("date")
        stop_p = float(p["stop_price"])
        target_p = float(p["target_price"])
        flat_by = p.get("flat_by", "15:15")

        new_rules.append({
            "id": "%s-stop" % sym.lower(),
            "type": "below",
            "symbol": sym,
            "price": stop_p,
            "date": date_str,
            "label": "plan stop loss hit @ ₹%.2f" % stop_p,
            "active": True,
        })
        new_rules.append({
            "id": "%s-target" % sym.lower(),
            "type": "above",
            "symbol": sym,
            "price": target_p,
            "date": date_str,
            "label": "plan target hit @ ₹%.2f" % target_p,
            "active": True,
        })
        new_rules.append({
            "id": "%s-flat" % sym.lower(),
            "type": "time",
            "at": flat_by,
            "date": date_str,
            "label": "MIS auto square-off time (%s IST)" % flat_by,
            "active": True,
        })
    elif args.opening_bell:
        new_rules.append({
            "id": "nse-opening-bell",
            "type": "opening_bell",
            "label": "NSE Opening Bell (09:15 AM IST)",
            "active": True,
        })
    elif args.at:
        new_rules.append({
            "id": "time-%s" % args.at.replace(":", ""),
            "type": "time",
            "at": args.at,
            "label": args.label or "time alert %s IST" % args.at,
            "active": True,
        })
    elif args.symbol:
        sym = clean_symbol(args.symbol)
        if args.stop:
            new_rules.append({
                "id": "%s-stop" % sym.lower(),
                "type": "below",
                "symbol": sym,
                "price": float(args.stop),
                "label": "stop loss alert @ ₹%.2f" % float(args.stop),
                "active": True,
            })
        if args.target:
            new_rules.append({
                "id": "%s-target" % sym.lower(),
                "type": "above",
                "symbol": sym,
                "price": float(args.target),
                "label": "target alert @ ₹%.2f" % float(args.target),
                "active": True,
            })
        if args.pct:
            new_rules.append({
                "id": "%s-pct" % sym.lower(),
                "type": "pct_move",
                "symbol": sym,
                "pct": float(args.pct),
                "label": "move >= %.1f%% alert" % float(args.pct),
                "active": True,
            })

    # Merge rules by ID
    existing_map = {r["id"]: r for r in rules}
    for nr in new_rules:
        existing_map[nr["id"]] = nr

    merged = list(existing_map.values())
    os.makedirs("trader", exist_ok=True)
    with open(alerts_file, "w", encoding="utf-8") as fh:
        json.dump({"rules": merged}, fh, indent=2)

    print("Added %d alert rule(s). Total active alerts: %d" % (len(new_rules), len(merged)))
    return 0


def run_check(args):
    now_utc = parse_now(args.now)
    now_ist = to_ist(now_utc)
    cur_time_str = now_ist.strftime("%H:%M")
    cur_date_str = now_ist.strftime("%Y-%m-%d")

    alerts_file = "trader/alerts.json"
    if not os.path.isfile(alerts_file):
        return 1

    with open(alerts_file, encoding="utf-8") as fh:
        rules = json.load(fh).get("rules", [])

    prices = {}
    if os.path.isfile("trader/prices.json"):
        try:
            with open("trader/prices.json", encoding="utf-8") as fh:
                prices = json.load(fh)
        except Exception:
            pass

    rang = []
    for r in rules:
        if not r.get("active", True):
            continue
        r_type = r.get("type")
        r_date = r.get("date")
        if r_date and r_date != cur_date_str:
            continue

        triggered = False
        reason = ""

        if r_type == "opening_bell":
            if now_ist.time() >= OPEN_TIME:
                triggered = True
                reason = "NSE Opening Bell reached (09:15 AM IST)"
        elif r_type == "time":
            if cur_time_str >= r.get("at", "15:30"):
                triggered = True
                reason = "Time passed %s IST" % r.get("at")
        elif r_type in ("above", "below", "pct_move"):
            sym = clean_symbol(r.get("symbol"))
            q = prices.get(sym)
            if not q and not args.offline:
                try:
                    q = fetch_quote(sym)
                    prices[sym] = q
                except Exception:
                    pass
            if q and "price" in q:
                p = float(q["price"])
                if r_type == "above" and p >= float(r.get("price", 0)):
                    triggered = True
                    reason = "Price ₹%.2f reached or exceeded target ₹%.2f" % (p, float(r["price"]))
                elif r_type == "below" and p <= float(r.get("price", 0)):
                    triggered = True
                    reason = "Price ₹%.2f dropped to or below stop ₹%.2f" % (p, float(r["price"]))

        if triggered:
            r["active"] = False
            r["triggered_at"] = now_ist.strftime("%Y-%m-%d %H:%M:%S IST")
            rang.append((r, reason))

    if rang:
        # Save updated active status
        with open(alerts_file, "w", encoding="utf-8") as fh:
            json.dump({"rules": rules}, fh, indent=2)

        print("RING! %d alert(s) triggered:" % len(rang))
        for r, reason in rang:
            print("  * [%s] %s: %s" % (r["id"], r.get("label", ""), reason))
        return 0

    return 1


def run_list(args):
    alerts_file = "trader/alerts.json"
    if not os.path.isfile(alerts_file):
        print("No alerts configured.")
        return 0
    with open(alerts_file, encoding="utf-8") as fh:
        rules = json.load(fh).get("rules", [])
    print("Configured Price & Time Alerts (%d total):" % len(rules))
    for r in rules:
        st = "[ACTIVE]" if r.get("active", True) else "[TRIGGERED]"
        print("  %-12s %-20s %s" % (st, r["id"], r.get("label", "")))
    return 0


def run_reset(args):
    alerts_file = "trader/alerts.json"
    if not os.path.isfile(alerts_file):
        return 1
    with open(alerts_file, encoding="utf-8") as fh:
        rules = json.load(fh).get("rules", [])
    found = False
    for r in rules:
        if r["id"] == args.alert_id:
            r["active"] = True
            r.pop("triggered_at", None)
            found = True
            break
    if found:
        with open(alerts_file, "w", encoding="utf-8") as fh:
            json.dump({"rules": rules}, fh, indent=2)
        print("Reset alert: %s (now active)" % args.alert_id)
        return 0
    print("Alert ID %r not found" % args.alert_id, file=sys.stderr)
    return 1


def main(argv=None):
    parser = argparse.ArgumentParser(description="Price Alerts & NSE Clock for Indian Equities.")
    sub = parser.add_subparsers(dest="subcommand", required=True)

    # clock
    p_cl = sub.add_parser("clock", help="Check NSE market clock and status")
    p_cl.add_argument("--now", help="Simulate clock (YYYY-MM-DD HH:MM IST)")
    p_cl.add_argument("--json", action="store_true")

    # quote
    p_q = sub.add_parser("quote", help="Fetch quotes for symbols")
    p_q.add_argument("symbol", nargs="?", help="Symbol (e.g. RELIANCE)")
    p_q.add_argument("--holdings", action="store_true", help="Fetch quotes for portfolio and plan")
    p_q.add_argument("--offline", help="Path to offline quote file or folder")
    p_q.add_argument("--write", action="store_true")
    p_q.add_argument("--no-write", action="store_true")
    p_q.add_argument("--json", action="store_true")

    # add
    p_a = sub.add_parser("add", help="Add alert rules")
    p_a.add_argument("--from-plan", action="store_true", help="Add alerts from trader/plan.json")
    p_a.add_argument("--symbol", help="Stock ticker")
    p_a.add_argument("--stop", type=float, help="Stop loss price")
    p_a.add_argument("--target", type=float, help="Target price")
    p_a.add_argument("--pct", type=float, help="Percent move from prev close")
    p_a.add_argument("--at", help="Time alert in HH:MM IST")
    p_a.add_argument("--label", help="Descriptive label")
    p_a.add_argument("--opening-bell", action="store_true", help="Add 09:15 AM opening bell alert")

    # check
    p_ch = sub.add_parser("check", help="Check prices and trigger alert bells")
    p_ch.add_argument("--now", help="Simulate clock")
    p_ch.add_argument("--offline", help="Path to offline quote folder")

    # list
    p_l = sub.add_parser("list", help="List all alerts")

    # reset
    p_r = sub.add_parser("reset", help="Reset a triggered alert rule")
    p_r.add_argument("alert_id", help="Alert rule ID to reset")

    args = parser.parse_args(argv)
    try:
        if args.subcommand == "clock":
            return run_clock(args)
        elif args.subcommand == "quote":
            return run_quote(args)
        elif args.subcommand == "add":
            return run_add(args)
        elif args.subcommand == "check":
            return run_check(args)
        elif args.subcommand == "list":
            return run_list(args)
        elif args.subcommand == "reset":
            return run_reset(args)
    except AlertError as err:
        print("error: %s" % err, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
