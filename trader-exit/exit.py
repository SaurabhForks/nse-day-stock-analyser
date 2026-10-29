#!/usr/bin/env python3
"""Exit Planner for Indian equities (NSE/BSE). Standard library only.

    python3 exit.py plan                                    # from trader/entry.json: or-mid stop, 2R target
    python3 exit.py plan --stop or-mid --target 1R --write  # stop 2480, target 2540
    python3 exit.py plan --symbol RELIANCE --entry 2500 --or-high 2490 --or-low 2470
    python3 exit.py plan --stop atr:1.5 --offline RELIANCE.json
    python3 exit.py show                                    # current trader/plan.json

Calculates stop-loss and profit target before you enter an Indian intraday trade.
Sets mandatory intraday exit at 15:15 IST (flat_by) before Indian brokers auto-square-off.
Writes trader/plan.json. Longs only. Never places an order.
"""

import argparse
import datetime
import gzip
import json
import os
import re
import sys
from decimal import Decimal, InvalidOperation, ROUND_FLOOR, ROUND_HALF_UP

UA = "Mozilla/5.0 (compatible; indian-day-trader-skill/2.0; +https://github.com/SaurabhTomar/indian-day-trader-skill)"
DEFAULTS = {"flat_by": "15:15", "min_reward_risk": 1.0}
ATR_BARS = 14
MIN_RISK_PCT = Decimal("0.05")
CENT = Decimal("0.05")  # Minimum tick size on NSE is ₹0.05 (5 paise)
NOTE = "A stop is a plan, not a guarantee: a gap or fast market can slip past it."


class PlanError(Exception):
    pass


def clean_symbol(sym):
    s = (sym or "").strip().upper()
    if s.endswith(".NS") or s.endswith(".BO"):
        s = s[:-3]
    return s


def round_tick(val, mode=ROUND_FLOOR):
    """Round to NSE minimum price tick (₹0.05)."""
    d = Decimal(str(val))
    # Round to nearest 0.05
    ticks = (d / Decimal("0.05")).quantize(Decimal("1"), rounding=mode)
    return (ticks * Decimal("0.05")).quantize(Decimal("0.01"))


def compute_atr(bars, period=14):
    """Compute Average True Range from 5-minute bars."""
    if len(bars) < 2:
        return None
    trs = []
    for i in range(1, len(bars)):
        h = bars[i]["high"]
        l = bars[i]["low"]
        prev_c = bars[i - 1]["close"]
        tr = max(h - l, abs(h - prev_c), abs(l - prev_c))
        trs.append(tr)
    if not trs:
        return None
    if len(trs) < period:
        return sum(trs) / len(trs)
    atr = sum(trs[:period]) / period
    for tr in trs[period:]:
        atr = (atr * (period - 1) + tr) / period
    return atr


def build_plan(symbol, entry_price, or_high=None, or_low=None, stop_rule="or-mid",
               target_rule="2R", flat_by="15:15", date_str=None, bars=None):
    """Create a validated day trading exit plan."""
    symbol = clean_symbol(symbol)
    entry = Decimal(str(entry_price)).quantize(Decimal("0.01"))

    # Resolve Stop Price
    stop_price = None
    stop_reason = ""

    if stop_rule == "or-mid":
        if or_high is None or or_low is None:
            raise PlanError("or-mid stop requires --or-high and --or-low (or trader/entry.json)")
        mid = (Decimal(str(or_high)) + Decimal(str(or_low))) / Decimal("2")
        stop_price = round_tick(mid, ROUND_FLOOR)
        stop_reason = "opening range midpoint (₹%.2f - ₹%.2f)" % (or_low, or_high)
    elif stop_rule == "or-low":
        if or_low is None:
            raise PlanError("or-low stop requires --or-low")
        stop_price = round_tick(or_low, ROUND_FLOOR)
        stop_reason = "opening range low"
    elif stop_rule.startswith("price:"):
        p = Decimal(stop_rule.split(":", 1)[1])
        stop_price = round_tick(p, ROUND_FLOOR)
        stop_reason = "fixed price stop"
    elif stop_rule.startswith("pct:"):
        pct = Decimal(stop_rule.split(":", 1)[1])
        p = entry * (Decimal("1") - pct / Decimal("100"))
        stop_price = round_tick(p, ROUND_FLOOR)
        stop_reason = "%.1f%% under entry" % float(pct)
    elif stop_rule.startswith("atr:"):
        k = Decimal(stop_rule.split(":", 1)[1])
        atr = compute_atr(bars or []) if bars else None
        if atr is None:
            raise PlanError("cannot compute ATR (requires intraday bars)")
        p = entry - (k * Decimal(str(atr)))
        stop_price = round_tick(p, ROUND_FLOOR)
        stop_reason = "%.1fx ATR (₹%.2f) below entry" % (float(k), atr)
    else:
        raise PlanError("unknown stop rule: %s" % stop_rule)

    if stop_price >= entry:
        raise PlanError("stop price (₹%.2f) must be lower than entry (₹%.2f)" % (stop_price, entry))

    risk_per_share = entry - stop_price
    min_risk = entry * (MIN_RISK_PCT / Decimal("100"))
    if risk_per_share < min_risk:
        raise PlanError("risk per share (₹%.2f) is below minimum %.2f%% threshold (₹%.2f)" % (
            risk_per_share, float(MIN_RISK_PCT), min_risk
        ))

    # Resolve Target Price
    target_price = None
    target_reason = ""

    if target_rule.endswith("R") or target_rule.endswith("r"):
        r_mult = Decimal(target_rule[:-1])
        target_price = round_tick(entry + (r_mult * risk_per_share), ROUND_HALF_UP)
        target_reason = "%s reward (₹%.2f risk)" % (target_rule.upper(), risk_per_share)
    elif target_rule.startswith("price:"):
        p = Decimal(target_rule.split(":", 1)[1])
        target_price = round_tick(p, ROUND_HALF_UP)
        target_reason = "fixed price target"
    else:
        raise PlanError("unknown target rule: %s" % target_rule)

    if target_price <= entry:
        raise PlanError("target price (₹%.2f) must be higher than entry (₹%.2f)" % (target_price, entry))

    reward_per_share = target_price - entry
    reward_risk_ratio = float(reward_per_share / risk_per_share)

    today = date_str or datetime.date.today().isoformat()

    return {
        "symbol": symbol,
        "side": "buy",
        "date": today,
        "entry_price": float(entry),
        "stop_price": float(stop_price),
        "target_price": float(target_price),
        "risk_per_share": float(risk_per_share),
        "reward_per_share": float(reward_per_share),
        "reward_risk_ratio": round(reward_risk_ratio, 2),
        "stop_rule": stop_rule,
        "stop_reason": stop_reason,
        "target_rule": target_rule,
        "target_reason": target_reason,
        "flat_by": flat_by,
        "exchange": "NSE",
        "product": "MIS",
        "note": NOTE,
    }


def run_plan(args):
    entry_data = {}
    if os.path.isfile("trader/entry.json"):
        try:
            with open("trader/entry.json", encoding="utf-8") as fh:
                entry_data = json.load(fh)
        except Exception:
            pass

    symbol = args.symbol or entry_data.get("symbol")
    if not symbol:
        raise PlanError("missing symbol (provide --symbol or run trader-entry first)")

    entry = args.entry or entry_data.get("entry_price")
    if not entry:
        raise PlanError("missing entry price (provide --entry or run trader-entry first)")

    or_high = args.or_high or entry_data.get("or_high")
    or_low = args.or_low or entry_data.get("or_low")
    date_str = args.date or entry_data.get("date")

    # Read config flat_by
    flat_by = DEFAULTS["flat_by"]
    if os.path.isfile("trader/config.json"):
        try:
            with open("trader/config.json", encoding="utf-8") as fh:
                cfg = json.load(fh)
                flat_by = cfg.get("flat_by", flat_by)
        except Exception:
            pass

    plan = build_plan(
        symbol=symbol,
        entry_price=entry,
        or_high=or_high,
        or_low=or_low,
        stop_rule=args.stop,
        target_rule=args.target,
        flat_by=flat_by,
        date_str=date_str,
    )

    if args.write or not args.no_write:
        os.makedirs("trader", exist_ok=True)
        with open("trader/plan.json", "w", encoding="utf-8") as fh:
            json.dump(plan, fh, indent=2)

    if args.json:
        print(json.dumps(plan, indent=2))
    else:
        print("Exit Plan for %s (NSE MIS):" % plan["symbol"])
        print("  Entry Price:  ₹%.2f" % plan["entry_price"])
        print("  Stop-Loss:    ₹%.2f (%s, risk ₹%.2f/sh)" % (
            plan["stop_price"], plan["stop_reason"], plan["risk_per_share"]
        ))
        print("  Target:       ₹%.2f (%s, reward ₹%.2f/sh, 1:%.2f R:R)" % (
            plan["target_price"], plan["target_reason"], plan["reward_per_share"], plan["reward_risk_ratio"]
        ))
        print("  Auto-Square:  %s IST (MIS flat by close)" % plan["flat_by"])
        print("  Note:         %s" % plan["note"])

    return 0


def run_show(args):
    if not os.path.isfile("trader/plan.json"):
        print("error: trader/plan.json not found", file=sys.stderr)
        return 1
    with open("trader/plan.json", encoding="utf-8") as fh:
        plan = json.load(fh)
    if args.json:
        print(json.dumps(plan, indent=2))
    else:
        print("Current Plan: %s | Entry: ₹%.2f | Stop: ₹%.2f | Target: ₹%.2f | R:R 1:%.2f | Flat by: %s" % (
            plan["symbol"], plan["entry_price"], plan["stop_price"],
            plan["target_price"], plan["reward_risk_ratio"], plan["flat_by"]
        ))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="Exit Planner for Indian Equities.")
    sub = parser.add_subparsers(dest="subcommand", required=True)

    p_p = sub.add_parser("plan", help="Create exit plan")
    p_p.add_argument("--symbol", help="Stock ticker (e.g. RELIANCE)")
    p_p.add_argument("--entry", type=float, help="Entry price in INR")
    p_p.add_argument("--or-high", type=float, help="Opening range high")
    p_p.add_argument("--or-low", type=float, help="Opening range low")
    p_p.add_argument("--stop", default="or-mid", help="Stop rule: or-mid (default), or-low, price:X, pct:X, atr:K")
    p_p.add_argument("--target", default="2R", help="Target rule: 2R (default), 1R, 1.5R, 3R, price:X")
    p_p.add_argument("--date", help="Trade date (YYYY-MM-DD)")
    p_p.add_argument("--write", action="store_true", help="Save trader/plan.json")
    p_p.add_argument("--no-write", action="store_true", help="Do not write file")
    p_p.add_argument("--json", action="store_true", help="Output JSON only")

    p_s = sub.add_parser("show", help="Display current trader/plan.json")
    p_s.add_argument("--json", action="store_true")

    args = parser.parse_args(argv)
    try:
        if args.subcommand == "plan":
            return run_plan(args)
        elif args.subcommand == "show":
            return run_show(args)
    except PlanError as err:
        print("error: %s" % err, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
