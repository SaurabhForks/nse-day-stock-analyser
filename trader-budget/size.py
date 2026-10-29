#!/usr/bin/env python3
"""Position Sizing and Statutory Charges Calculator for Indian Equities. Standard library only.

    python3 size.py                                  # trader/plan.json + trader/config.json
    python3 size.py --write                          # write trader/orders.json
    python3 size.py --limit                          # limit order at the plan's entry price
    python3 size.py --limit 2505.00 --write          # limit order at custom price
    python3 size.py --budget 100000 --max-loss 1000  # override budget & max loss in INR

Sizes an intraday position in whole shares to your risk budget (INR ₹). Calculates
exact Indian statutory taxes and charges (STT, NSE transaction charge, SEBI turnover fee,
Stamp Duty, GST, and broker commission). Formats bracket order for Indian brokers (MIS product).
Never places an order.
"""

import argparse
import datetime
import json
import math
import os
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
    "no_entries_after": "14:45",
    "flat_by": "15:15",
    "intraday_leverage": 5.0,  # 5x leverage for MIS cash equity under SEBI peak margin rules
    "broker": "zerodha",
    "paper": True,
    "blocked": [],
    "allow_options": False,
    "allow_margin": False,
    "allow_short": False,
}

EPS = 1e-9


class SizeError(Exception):
    pass


def clean_symbol(sym):
    s = (sym or "").strip().upper()
    if s.endswith(".NS") or s.endswith(".BO"):
        s = s[:-3]
    return s


# ---------------------------------------------------------------- Indian Taxes & Charges

def calculate_indian_charges(buy_price, sell_price, qty, is_intraday=True):
    """Calculate exact Indian regulatory taxes, exchange fees, and brokerage for equity trading.

    Components (Intraday Equity):
      - STT (Securities Transaction Tax): 0.025% on sell turnover
      - NSE Transaction Charge: 0.00297% on total turnover
      - SEBI Turnover Fee: ₹10 per crore (0.0001%) on total turnover
      - Stamp Duty: 0.003% on buy turnover
      - Brokerage: ₹20 flat or 0.03% (whichever is lower) per executed order
      - GST: 18% on (Brokerage + NSE charges + SEBI charges)
    """
    buy_turnover = buy_price * qty
    sell_turnover = sell_price * qty
    total_turnover = buy_turnover + sell_turnover

    # 1. STT: 0.025% on sell side only for intraday
    stt = round(0.00025 * sell_turnover, 2) if is_intraday else round(0.001 * total_turnover, 2)

    # 2. Exchange Transaction Charges (NSE): 0.00297%
    nse_charges = round(0.0000297 * total_turnover, 2)

    # 3. SEBI Turnover Fee: ₹10 per crore (0.0001%)
    sebi_fee = round(0.000001 * total_turnover, 2)

    # 4. Stamp Duty (State Govt): 0.003% on buy side only
    stamp_duty = round(0.00003 * buy_turnover, 2)

    # 5. Brokerage: ₹20 or 0.03% per leg (discount broker standard like Zerodha/Groww/Angel)
    buy_brokerage = min(20.0, round(0.0003 * buy_turnover, 2))
    sell_brokerage = min(20.0, round(0.0003 * sell_turnover, 2))
    brokerage = round(buy_brokerage + sell_brokerage, 2)

    # 6. GST: 18% on Brokerage + Transaction Charges + SEBI Fee
    gst_taxable = brokerage + nse_charges + sebi_fee
    gst = round(0.18 * gst_taxable, 2)

    total_charges = round(stt + nse_charges + sebi_fee + stamp_duty + brokerage + gst, 2)
    breakeven_per_share = round(total_charges / qty, 2) if qty > 0 else 0.0

    return {
        "stt": stt,
        "nse_charges": nse_charges,
        "sebi_fee": sebi_fee,
        "stamp_duty": stamp_duty,
        "brokerage": brokerage,
        "gst": gst,
        "total_charges": total_charges,
        "breakeven_per_share": breakeven_per_share,
    }


# ---------------------------------------------------------------- Position Sizer

def calculate_shares(entry_price, stop_price, config, portfolio=None):
    """Calculate allowable whole shares based on risk budget and margin limits."""
    risk_per_share = entry_price - stop_price
    if risk_per_share <= 0:
        raise SizeError("invalid risk per share (entry ₹%.2f <= stop ₹%.2f)" % (entry_price, stop_price))

    budget = float(config.get("budget_inr") or config.get("budget") or DEFAULTS["budget_inr"])
    max_loss = float(config.get("max_loss_per_trade_inr") or config.get("max_loss_per_trade_usd") or DEFAULTS["max_loss_per_trade_inr"])
    max_order = float(config.get("max_order_inr") or config.get("max_order_usd") or DEFAULTS["max_order_inr"])
    max_pos_pct = float(config.get("max_position_pct", DEFAULTS["max_position_pct"]))
    leverage = float(config.get("intraday_leverage", DEFAULTS["intraday_leverage"]))
    cash_buf_pct = float(config.get("cash_buffer_pct", DEFAULTS["cash_buffer_pct"]))

    # Cash constraint
    avail_cash = budget * (1.0 - (cash_buf_pct / 100.0))
    if portfolio and "cash" in portfolio:
        avail_cash = min(avail_cash, float(portfolio["cash"]))

    # 1. Share limit from risk budget (Max Loss)
    shares_risk = math.floor(max_loss / risk_per_share)

    # 2. Share limit from position cap
    max_pos_val = budget * (max_pos_pct / 100.0)
    shares_pos = math.floor(max_pos_val / (entry_price / leverage))

    # 3. Share limit from max order size
    shares_order = math.floor(max_order / (entry_price / leverage))

    # 4. Share limit from available cash
    shares_cash = math.floor(avail_cash / (entry_price / leverage))

    shares = min(shares_risk, shares_pos, shares_order, shares_cash)
    if shares <= 0:
        raise SizeError(
            "calculated 0 shares (risk per share ₹%.2f exceeds max loss ₹%.2f or cash is insufficient)" % (
                risk_per_share, max_loss
            )
        )

    return {
        "shares": int(shares),
        "shares_risk_limit": int(shares_risk),
        "shares_pos_limit": int(shares_pos),
        "shares_order_limit": int(shares_order),
        "shares_cash_limit": int(shares_cash),
        "risk_per_share": round(risk_per_share, 2),
    }


def size_trade(plan, config, limit_price=None, portfolio=None):
    symbol = clean_symbol(plan["symbol"])
    entry = float(limit_price if limit_price is not None else plan["entry_price"])
    stop = float(plan["stop_price"])
    target = float(plan["target_price"])

    res = calculate_shares(entry, stop, config, portfolio)
    qty = res["shares"]

    # Calculate capital and margin
    leverage = float(config.get("intraday_leverage", DEFAULTS["intraday_leverage"]))
    notional_val = round(entry * qty, 2)
    margin_required = round(notional_val / leverage, 2)
    max_loss_at_stop = round((entry - stop) * qty, 2)
    gross_profit_target = round((target - entry) * qty, 2)

    # Taxes and Charges
    charges_target = calculate_indian_charges(entry, target, qty, is_intraday=True)
    charges_stop = calculate_indian_charges(entry, stop, qty, is_intraday=True)

    net_target_pnl = round(gross_profit_target - charges_target["total_charges"], 2)
    net_stop_loss = round(max_loss_at_stop + charges_stop["total_charges"], 2)

    order = {
        "symbol": symbol,
        "exchange": "NSE",
        "product": "MIS",
        "side": "buy",
        "qty": qty,
        "order_type": "limit" if limit_price is not None else "market",
        "entry_price": entry,
        "limit_price": entry if limit_price is not None else None,
        "stop_loss_price": stop,
        "take_profit_price": target,
        "notional_value_inr": notional_val,
        "margin_required_inr": margin_required,
        "max_loss_inr": max_loss_at_stop,
        "gross_reward_inr": gross_profit_target,
        "statutory_charges_target_inr": charges_target["total_charges"],
        "statutory_charges_stop_inr": charges_stop["total_charges"],
        "net_profit_target_inr": net_target_pnl,
        "net_loss_stop_inr": net_stop_loss,
        "breakeven_points_inr": charges_target["breakeven_per_share"],
        "charges_breakdown": charges_target,
        "time_in_force": "day",
        "order_class": "bracket",
    }

    return order


def run_size(args):
    # Load plan
    if not os.path.isfile("trader/plan.json"):
        raise SizeError("trader/plan.json not found (run trader-exit first)")
    with open("trader/plan.json", encoding="utf-8") as fh:
        plan = json.load(fh)

    # Load config
    cfg = dict(DEFAULTS)
    if os.path.isfile("trader/config.json"):
        try:
            with open("trader/config.json", encoding="utf-8") as fh:
                user_cfg = json.load(fh)
                cfg.update(user_cfg)
        except Exception:
            pass

    # CLI overrides
    if args.budget:
        cfg["budget_inr"] = args.budget
    if args.max_loss:
        cfg["max_loss_per_trade_inr"] = args.max_loss

    # Load portfolio if exists
    portfolio = None
    if os.path.isfile("trader/portfolio.json"):
        try:
            with open("trader/portfolio.json", encoding="utf-8") as fh:
                portfolio = json.load(fh)
        except Exception:
            pass

    limit_p = None
    if args.limit is not None:
        limit_p = args.limit if args.limit > 0 else plan["entry_price"]

    order = size_trade(plan, cfg, limit_price=limit_p, portfolio=portfolio)
    orders_data = {
        "orders": [order],
        "created_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S IST"),
    }

    if args.write:
        os.makedirs("trader", exist_ok=True)
        with open("trader/orders.json", "w", encoding="utf-8") as fh:
            json.dump(orders_data, fh, indent=2)

    if args.json:
        print(json.dumps(orders_data, indent=2))
    else:
        print("Sized Order for %s (NSE MIS Bracket):" % order["symbol"])
        print("  Quantity:         %d shares" % order["qty"])
        print("  Entry Price:      ₹%.2f (%s)" % (order["entry_price"], order["order_type"].upper()))
        print("  Notional Value:   ₹%.2f (Margin @ 5x: ₹%.2f)" % (
            order["notional_value_inr"], order["margin_required_inr"]
        ))
        print("  Stop-Loss:        ₹%.2f (Gross loss: ₹%.2f | Net with charges: ₹%.2f)" % (
            order["stop_loss_price"], order["max_loss_inr"], order["net_loss_stop_inr"]
        ))
        print("  Take-Profit:      ₹%.2f (Gross profit: ₹%.2f | Net with charges: ₹%.2f)" % (
            order["take_profit_price"], order["gross_reward_inr"], order["net_profit_target_inr"]
        ))
        print("  Statutory Taxes:  ₹%.2f (STT: ₹%.2f, Brokerage: ₹%.2f, GST: ₹%.2f, NSE: ₹%.2f)" % (
            order["statutory_charges_target_inr"],
            order["charges_breakdown"]["stt"],
            order["charges_breakdown"]["brokerage"],
            order["charges_breakdown"]["gst"],
            order["charges_breakdown"]["nse_charges"]
        ))
        print("  Breakeven Move:   ₹%.2f / share" % order["breakeven_points_inr"])

    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="Position Sizing & Statutory Charges for Indian Day Trading.")
    parser.add_argument("--budget", type=float, help="Capital budget in INR (₹)")
    parser.add_argument("--max-loss", type=float, help="Max loss per trade in INR (₹)")
    parser.add_argument("--limit", type=float, nargs="?", const=0.0, help="Place as limit order")
    parser.add_argument("--write", action="store_true", help="Write trader/orders.json")
    parser.add_argument("--json", action="store_true", help="Output JSON only")

    args = parser.parse_args(argv)
    try:
        return run_size(args)
    except SizeError as err:
        print("error: %s" % err, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
