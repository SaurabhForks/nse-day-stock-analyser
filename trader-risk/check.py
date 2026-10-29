#!/usr/bin/env python3
"""Pre-trade Risk Manager for Indian Equities (NSE/BSE). Standard library only.

    python3 check.py                                 # check trader/orders.json, writes trader/state/risk.json
    python3 check.py --now "2026-10-19 10:15"        # pin the clock (IST time)
    python3 check.py --orders trader/orders.json --json
    python3 check.py --no-write                      # check without recording verdicts

Validates proposed orders against account rules, statutory guidelines, risk limits,
and NSE trading session windows. Every order receives PASS or BLOCK with full reasoning.
Never places an order.
"""

import argparse
import datetime
import hashlib
import json
import os
import re
import sys

DEFAULTS = {
    "budget_inr": 100000.0,
    "cash_buffer_pct": 10.0,
    "max_position_pct": 50.0,
    "max_order_inr": 50000.0,
    "min_order_inr": 500.0,
    "max_loss_per_trade_inr": 1000.0,
    "max_daily_loss_inr": 3000.0,
    "max_trades_per_day": 3,
    "max_orders_per_day": 10,
    "min_reward_risk": 1.0,
    "require_stop": True,
    "no_entries_before": "09:30",
    "no_entries_after": "10:15",
    "flat_by": "15:15",
    "intraday_leverage": 5.0,
    "paper": True,
    "blocked": [],
    "allow_options": False,
    "allow_margin": False,
    "allow_short": False,
    "nifty_filter": False,
    "max_nifty_drop_pct": -1.0,
}

NSE_HOLIDAYS = {
    "2026-01-26": "Republic Day", "2026-03-03": "Holi", "2026-03-20": "Id-ul-Fitr",
    "2026-03-27": "Ram Navami", "2026-04-03": "Good Friday", "2026-04-14": "Dr. Ambedkar Jayanti",
    "2026-05-01": "Maharashtra Day", "2026-05-27": "Bakri Id", "2026-06-25": "Moharram",
    "2026-08-15": "Independence Day", "2026-10-02": "Mahatma Gandhi Jayanti", "2026-10-20": "Dussehra",
    "2026-11-08": "Diwali Laxmi Pujan", "2026-11-10": "Diwali Balipratipada",
    "2026-11-24": "Gurunanak Jayanti", "2026-12-25": "Christmas",
}

MARKET_OPEN = datetime.time(9, 15)
MARKET_CLOSE = datetime.time(15, 30)


class RiskError(Exception):
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
            raise RiskError("cannot parse date/time: %r" % text)
    if dt.tzinfo is not None:
        return dt.astimezone(datetime.timezone.utc).replace(microsecond=0, tzinfo=None)
    return ist_to_utc(dt).replace(microsecond=0)


def order_fingerprint(order):
    """Generate SHA256 fingerprint for an order."""
    keys = sorted(order.keys())
    s = "|".join("%s=%s" % (k, order[k]) for k in keys if k not in ("fingerprint", "charges_breakdown"))
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


def is_market_open_ist(dt_ist):
    """Check if NSE is open at given IST datetime."""
    d = dt_ist.date()
    if d.weekday() >= 5:
        return False, "market is closed on weekends"
    d_iso = d.isoformat()
    if d_iso in NSE_HOLIDAYS and "Muhurat" not in NSE_HOLIDAYS[d_iso]:
        return False, "market is closed today (%s)" % NSE_HOLIDAYS[d_iso]
    t = dt_ist.time()
    if t < MARKET_OPEN or t >= MARKET_CLOSE:
        return False, "outside NSE trading hours (09:15 to 15:30 IST)"
    return True, "open"


def check_order(order, config, portfolio, broker_state, prices, now_ist):
    reasons = []
    symbol = clean_symbol(order.get("symbol"))
    side = (order.get("side") or "").lower()
    qty = order.get("qty", 0)
    entry = float(order.get("limit_price") or order.get("entry_price") or 0.0)
    stop = float(order.get("stop_loss_price") or 0.0)
    target = float(order.get("take_profit_price") or 0.0)
    order_type = (order.get("order_type") or "market").lower()

    budget = float(config.get("budget_inr") or config.get("budget") or DEFAULTS["budget_inr"])
    max_loss_trade = float(config.get("max_loss_per_trade_inr") or config.get("max_loss_per_trade_usd") or DEFAULTS["max_loss_per_trade_inr"])
    max_daily_loss = float(config.get("max_daily_loss_inr") or config.get("max_daily_loss_usd") or DEFAULTS["max_daily_loss_inr"])
    max_order_val = float(config.get("max_order_inr") or config.get("max_order_usd") or DEFAULTS["max_order_inr"])
    min_order_val = float(config.get("min_order_inr") or config.get("min_order_usd") or DEFAULTS["min_order_inr"])
    max_pos_pct = float(config.get("max_position_pct", DEFAULTS["max_position_pct"]))
    min_rr = float(config.get("min_reward_risk", DEFAULTS["min_reward_risk"]))
    require_stop = bool(config.get("require_stop", DEFAULTS["require_stop"]))
    max_trades_day = int(config.get("max_trades_per_day", DEFAULTS["max_trades_per_day"]))
    max_orders_day = int(config.get("max_orders_per_day", DEFAULTS["max_orders_per_day"]))

    # 1. Format validation
    if not symbol:
        reasons.append("missing symbol")
    if side not in ("buy", "sell"):
        reasons.append("invalid side: %r" % side)
    if not isinstance(qty, int) or qty <= 0:
        reasons.append("invalid quantity (must be positive whole shares): %r" % qty)
    if entry <= 0:
        reasons.append("invalid entry price: ₹%.2f" % entry)

    # 2. Blocked symbol
    blocked_list = [clean_symbol(s) for s in config.get("blocked", [])]
    if symbol in blocked_list:
        reasons.append("symbol %s is in blocked list" % symbol)

    # 3. Market session & holiday check
    is_open, open_reason = is_market_open_ist(now_ist)
    if not is_open:
        reasons.append(open_reason)

    # 4. Entry time window
    cur_time = now_ist.strftime("%H:%M")
    w_start = config.get("no_entries_before", DEFAULTS["no_entries_before"])
    w_end = config.get("no_entries_after", DEFAULTS["no_entries_after"])
    if cur_time < w_start:
        reasons.append("current time %s IST is before entry window %s IST" % (cur_time, w_start))
    if cur_time > w_end:
        reasons.append("current time %s IST is after entry window %s IST" % (cur_time, w_end))

    # 5. Stop Loss Check
    if require_stop:
        if stop <= 0:
            reasons.append("stop-loss is required by risk configuration")
        elif side == "buy" and stop >= entry:
            reasons.append("stop-loss ₹%.2f is at or above entry price ₹%.2f" % (stop, entry))

    # 6. Reward to Risk Check
    if stop > 0 and target > 0 and entry > stop:
        risk = entry - stop
        reward = target - entry
        rr = reward / risk
        if rr < min_rr:
            reasons.append("reward:risk ratio 1:%.2f is below minimum 1:%.2f" % (rr, min_rr))

    # 7. Max Loss Per Trade Check
    if stop > 0 and entry > stop:
        trade_loss = (entry - stop) * qty
        if trade_loss > max_loss_trade:
            reasons.append("max loss ₹%.2f exceeds limit ₹%.2f" % (trade_loss, max_loss_trade))

    # 8. Order Size & Position Cap
    order_val = entry * qty
    leverage = float(config.get("intraday_leverage", DEFAULTS["intraday_leverage"]))
    margin_val = order_val / leverage

    if margin_val < min_order_val:
        reasons.append("margin value ₹%.2f is under minimum ₹%.2f" % (margin_val, min_order_val))
    if margin_val > max_order_val:
        reasons.append("margin value ₹%.2f exceeds max order limit ₹%.2f" % (margin_val, max_order_val))

    max_pos_val = budget * (max_pos_pct / 100.0)
    if margin_val > max_pos_val:
        reasons.append("margin value ₹%.2f exceeds %.0f%% cap (₹%.2f)" % (margin_val, max_pos_pct, max_pos_val))

    # 9. Daily limits (orders placed today)
    placed_today = broker_state.get("orders_placed_today", [])
    if len(placed_today) >= max_orders_day:
        reasons.append("daily order limit of %d reached" % max_orders_day)

    entries_today = [o for o in placed_today if o.get("side") == "buy"]
    if len(entries_today) >= max_trades_day:
        reasons.append("daily trade limit of %d entries reached" % max_trades_day)

    # 10. Daily Loss Limit
    accum_loss = sum(float(o.get("max_loss_inr", 0)) for o in entries_today)
    this_loss = (entry - stop) * qty if stop > 0 and entry > stop else 0.0
    if (accum_loss + this_loss) > max_daily_loss:
        reasons.append("combined daily risk ₹%.2f exceeds max daily loss ₹%.2f" % (
            accum_loss + this_loss, max_daily_loss
        ))

    # 11. Duplicate check
    for o in placed_today:
        if clean_symbol(o.get("symbol")) == symbol and o.get("side") == side:
            reasons.append("duplicate order: %s %s already placed today" % (side.upper(), symbol))
            break

    # 12. Broad Market Trend / Nifty 50 Alignment Filter
    nifty_filter_enabled = bool(config.get("nifty_filter") or config.get("require_market_alignment", False))
    market_change = order.get("nifty_change_pct") if "nifty_change_pct" in order else order.get("market_change_pct")
    if market_change is None and prices:
        nifty_q = prices.get("^NSEI") or prices.get("NIFTY") or prices.get("NIFTY 50")
        if isinstance(nifty_q, dict):
            p = float(nifty_q.get("price") or 0.0)
            pc = float(nifty_q.get("prev_close") or 0.0)
            if pc > 0:
                market_change = ((p - pc) / pc) * 100.0
            elif "change_pct" in nifty_q:
                market_change = float(nifty_q["change_pct"])

    if nifty_filter_enabled and market_change is not None:
        max_market_drop = float(config.get("max_nifty_drop_pct", -1.0))
        if side == "buy" and float(market_change) < max_market_drop:
            reasons.append("broad market risk: Nifty 50 is down %.2f%% (bearish trend blocks long breakouts)" % float(market_change))

    status = "BLOCK" if reasons else "PASS"
    return status, reasons


def run_check(args):
    now_utc = parse_now(args.now)
    now_ist = to_ist(now_utc)

    # Load orders
    orders_path = args.orders or "trader/orders.json"
    if not os.path.isfile(orders_path):
        raise RiskError("orders file not found: %s" % orders_path)
    with open(orders_path, encoding="utf-8") as fh:
        raw_orders = json.load(fh)
    order_list = raw_orders.get("orders", [])
    if not order_list:
        raise RiskError("no orders found in %s" % orders_path)

    # Load config
    cfg = dict(DEFAULTS)
    if os.path.isfile("trader/config.json"):
        try:
            with open("trader/config.json", encoding="utf-8") as fh:
                cfg.update(json.load(fh))
        except Exception:
            pass

    if args.nifty_filter:
        cfg["nifty_filter"] = True

    # Load portfolio
    portfolio = {}
    if os.path.isfile("trader/portfolio.json"):
        try:
            with open("trader/portfolio.json", encoding="utf-8") as fh:
                portfolio = json.load(fh)
        except Exception:
            pass

    # Load broker state
    broker_state = {}
    if os.path.isfile("trader/state/broker.json"):
        try:
            with open("trader/state/broker.json", encoding="utf-8") as fh:
                broker_state = json.load(fh)
        except Exception:
            pass

    # Load prices
    prices = {}
    if os.path.isfile("trader/prices.json"):
        try:
            with open("trader/prices.json", encoding="utf-8") as fh:
                prices = json.load(fh)
        except Exception:
            pass

    verdicts = []
    all_passed = True

    for ord_obj in order_list:
        fp = order_fingerprint(ord_obj)
        status, reasons = check_order(ord_obj, cfg, portfolio, broker_state, prices, now_ist)
        if status == "BLOCK":
            all_passed = False
        verdicts.append({
            "fingerprint": fp,
            "symbol": clean_symbol(ord_obj.get("symbol")),
            "side": ord_obj.get("side"),
            "qty": ord_obj.get("qty"),
            "status": status,
            "reasons": reasons,
        })

    out_data = {
        "as_of": now_ist.strftime("%Y-%m-%d %H:%M:%S IST"),
        "all_passed": all_passed,
        "verdicts": verdicts,
    }

    if not args.no_write:
        os.makedirs("trader/state", exist_ok=True)
        with open("trader/state/risk.json", "w", encoding="utf-8") as fh:
            json.dump(out_data, fh, indent=2)

    if args.json:
        print(json.dumps(out_data, indent=2))
    else:
        print("Pre-Trade Risk Check as of %s:" % out_data["as_of"])
        for v in verdicts:
            sym = v["symbol"]
            st = v["status"]
            if st == "PASS":
                print("  [PASS]  %-10s %s %d shares - cleared all risk rules" % (sym, v["side"].upper(), v["qty"]))
            else:
                print("  [BLOCK] %-10s %s %d shares - blocked:" % (sym, v["side"].upper(), v["qty"]))
                for r in v["reasons"]:
                    print("          * %s" % r)

    return 0 if all_passed else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description="Pre-Trade Risk Check for Indian Stock Market.")
    parser.add_argument("--orders", help="Path to orders.json")
    parser.add_argument("--nifty-filter", action="store_true", help="Block long entries when Nifty 50 is down > 1.0%")
    parser.add_argument("--now", help="Simulate clock (YYYY-MM-DD HH:MM IST)")
    parser.add_argument("--no-write", action="store_true", help="Do not write trader/state/risk.json")
    parser.add_argument("--json", action="store_true", help="Output JSON only")

    args = parser.parse_args(argv)
    try:
        return run_check(args)
    except RiskError as err:
        print("error: %s" % err, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
