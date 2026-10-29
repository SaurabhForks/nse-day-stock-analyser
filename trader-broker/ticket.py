#!/usr/bin/env python3
"""Broker Ticket and Order Execution Engine for Indian Brokers. Standard library only.

Supported Indian Brokers: Zerodha Kite Connect, Groww, Angel One, Upstox, Dhan.
Paper trading simulation by default. Never places an order without explicit user confirmation.

    python3 ticket.py show                    # show tickets, READY or not
    python3 ticket.py show --index 1 --json   # one ticket as broker JSON
    python3 ticket.py approve --index 1 --reply "yes RELIANCE"
    python3 ticket.py result --index 1 --status placed --broker-id 2410190001
    python3 ticket.py fill --symbol RELIANCE --side buy --qty 10 --price 2500.00
    python3 ticket.py flatten --symbol RELIANCE --qty 10  # generate MIS square-off order
    python3 ticket.py log
"""

import argparse
import datetime
import hashlib
import json
import os
import re
import sys

YES_WORDS = ("yes", "y")
BATCH_WORDS = {"all", "every", "everything", "rest", "remaining", "them", "both", "batch", "each"}
DOUBT_WORDS = {"no", "not", "dont", "don't", "wait", "cancel", "stop", "but", "maybe", "later", "hold", "unless"}


class TicketError(Exception):
    pass


def clean_symbol(sym):
    s = (sym or "").strip().upper()
    if s.endswith(".NS") or s.endswith(".BO"):
        s = s[:-3]
    return s


def to_ist(utc):
    return utc.replace(tzinfo=None) + datetime.timedelta(hours=5, minutes=30)


def ist_to_utc(ist):
    return ist - datetime.timedelta(hours=5, minutes=30)


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
            raise TicketError("cannot parse date/time: %r" % text)
    if dt.tzinfo is not None:
        return dt.astimezone(datetime.timezone.utc).replace(microsecond=0, tzinfo=None)
    return ist_to_utc(dt).replace(microsecond=0)


def order_fingerprint(order):
    keys = sorted(order.keys())
    s = "|".join("%s=%s" % (k, order[k]) for k in keys if k not in ("fingerprint", "charges_breakdown"))
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


def format_zerodha_kite_payload(order):
    """Format standard order into Zerodha Kite Connect API payload."""
    sym = clean_symbol(order["symbol"])
    side = order["side"].upper()
    qty = int(order["qty"])
    o_type = order.get("order_type", "limit").upper()
    price = float(order.get("limit_price") or order.get("entry_price") or 0.0)
    stop = float(order.get("stop_loss_price") or 0.0)
    target = float(order.get("take_profit_price") or 0.0)

    payload = {
        "tradingsymbol": sym,
        "exchange": "NSE",
        "transaction_type": side,
        "quantity": qty,
        "product": "MIS",
        "order_type": o_type,
        "price": price if o_type == "LIMIT" else 0.0,
        "validity": "DAY",
        "tag": "indian_day_trader",
    }
    if stop > 0:
        payload["stoploss"] = round(abs(price - stop), 2)
    if target > 0:
        payload["squareoff"] = round(abs(target - price), 2)
    return payload


def is_explicit_yes(reply, symbol=None, qty=None):
    """Strictly validates explicit user confirmation. Rejects ambiguous phrases."""
    clean = re.sub(r"[^\w\s]", "", (reply or "").lower()).split()
    if not clean:
        return False, "empty reply"

    # Check for doubt or negative words
    for w in clean:
        if w in DOUBT_WORDS:
            return False, "reply contains hesitant or negative word: %r" % w

    # Reject batch words
    for w in clean:
        if w in BATCH_WORDS:
            return False, "batch or blanket approval not permitted ('%s')" % w

    # Must contain 'yes' or 'y'
    if not any(w in YES_WORDS for w in clean):
        return False, "reply must explicitly contain 'yes'"

    # If symbol provided, verify it is mentioned or plain single-word yes
    if len(clean) > 1 and symbol:
        sym_clean = clean_symbol(symbol).lower()
        if sym_clean not in clean and not any(str(qty) in w for w in clean):
            return False, "reply must refer to ticker %s or order amount" % symbol

    return True, "valid explicit yes"


def run_show(args):
    now_utc = parse_now(args.now)
    now_ist = to_ist(now_utc)

    if not os.path.isfile("trader/orders.json"):
        print("error: trader/orders.json not found", file=sys.stderr)
        return 1
    with open("trader/orders.json", encoding="utf-8") as fh:
        orders_data = json.load(fh)
    order_list = orders_data.get("orders", [])

    # Load risk state
    risk_state = {}
    if os.path.isfile("trader/state/risk.json"):
        try:
            with open("trader/state/risk.json", encoding="utf-8") as fh:
                risk_state = json.load(fh)
        except Exception:
            pass
    verdicts = {v["fingerprint"]: v for v in risk_state.get("verdicts", [])}

    # Load broker state
    broker_state = {}
    if os.path.isfile("trader/state/broker.json"):
        try:
            with open("trader/state/broker.json", encoding="utf-8") as fh:
                broker_state = json.load(fh)
        except Exception:
            pass
    decisions = broker_state.get("decisions", {})

    tickets = []
    for idx, ord_obj in enumerate(order_list, start=1):
        fp = order_fingerprint(ord_obj)
        v = verdicts.get(fp)
        is_passed = (v and v.get("status") == "PASS")
        is_decided = fp in decisions

        ready = (is_passed and not is_decided)
        kite_payload = format_zerodha_kite_payload(ord_obj)

        tickets.append({
            "index": idx,
            "fingerprint": fp,
            "symbol": clean_symbol(ord_obj["symbol"]),
            "ready": ready,
            "risk_status": v.get("status") if v else "UNCHECKED",
            "decision": decisions.get(fp),
            "order": ord_obj,
            "kite_payload": kite_payload,
        })

    if args.index:
        if args.index < 1 or args.index > len(tickets):
            raise TicketError("invalid ticket index %d (available: 1..%d)" % (args.index, len(tickets)))
        t = tickets[args.index - 1]
        if args.json:
            print(json.dumps(t, indent=2))
        else:
            print(json.dumps(t["kite_payload"], indent=2))
        return 0

    if args.json:
        print(json.dumps(tickets, indent=2))
        return 0

    print("Order Tickets as of %s:" % now_ist.strftime("%Y-%m-%d %H:%M:%S IST"))
    for t in tickets:
        status_label = "[READY FOR APPROVAL]" if t["ready"] else "[NOT READY - %s]" % t["risk_status"]
        ord_info = t["order"]
        print("-" * 65)
        print("Ticket #%d: %s %s" % (t["index"], t["symbol"], status_label))
        print("  Side:        %s %d shares of %s" % (ord_info["side"].upper(), ord_info["qty"], ord_info["symbol"]))
        print("  Order Type:  %s @ ₹%.2f (Product: MIS Intraday)" % (
            ord_info["order_type"].upper(), ord_info["entry_price"]
        ))
        print("  Stop Loss:   ₹%.2f (Max loss: ₹%.2f)" % (ord_info["stop_loss_price"], ord_info["max_loss_inr"]))
        print("  Target:      ₹%.2f (Reward: ₹%.2f)" % (ord_info["take_profit_price"], ord_info["gross_reward_inr"]))
        print("  Broker JSON: %s" % json.dumps(t["kite_payload"]))

    return 0


def run_approve(args):
    if not os.path.isfile("trader/orders.json"):
        raise TicketError("trader/orders.json not found")
    with open("trader/orders.json", encoding="utf-8") as fh:
        orders = json.load(fh).get("orders", [])
    if args.index < 1 or args.index > len(orders):
        raise TicketError("index %d out of bounds" % args.index)

    order = orders[args.index - 1]
    fp = order_fingerprint(order)

    # Validate risk pass
    risk_state = {}
    if os.path.isfile("trader/state/risk.json"):
        with open("trader/state/risk.json", encoding="utf-8") as fh:
            risk_state = json.load(fh)
    v_map = {v["fingerprint"]: v for v in risk_state.get("verdicts", [])}
    if v_map.get(fp, {}).get("status") != "PASS":
        raise TicketError("order cannot be approved: it did not PASS pre-trade risk check")

    ok, reason = is_explicit_yes(args.reply, order["symbol"], order["qty"])
    if not ok:
        raise TicketError("approval rejected: %s" % reason)

    # Record in broker state
    broker_state = {"decisions": {}, "orders_placed_today": []}
    if os.path.isfile("trader/state/broker.json"):
        try:
            with open("trader/state/broker.json", encoding="utf-8") as fh:
                broker_state = json.load(fh)
        except Exception:
            pass

    broker_state.setdefault("decisions", {})[fp] = {
        "status": "approved",
        "reply": args.reply,
        "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S IST"),
    }
    os.makedirs("trader/state", exist_ok=True)
    with open("trader/state/broker.json", "w", encoding="utf-8") as fh:
        json.dump(broker_state, fh, indent=2)

    print("Order #%d (%s) APPROVED by user: %r" % (args.index, order["symbol"], args.reply))
    return 0


def run_result(args):
    state_file = "trader/state/broker.json"
    broker_state = {"decisions": {}, "orders_placed_today": []}
    if os.path.isfile(state_file):
        try:
            with open(state_file, encoding="utf-8") as fh:
                broker_state = json.load(fh)
        except Exception:
            pass

    orders = []
    if os.path.isfile("trader/orders.json"):
        with open("trader/orders.json", encoding="utf-8") as fh:
            orders = json.load(fh).get("orders", [])

    order = orders[args.index - 1] if 1 <= args.index <= len(orders) else {}
    placed_entry = {
        "symbol": order.get("symbol"),
        "side": order.get("side"),
        "qty": order.get("qty"),
        "status": args.status,
        "broker_id": args.broker_id,
        "max_loss_inr": order.get("max_loss_inr", 0),
        "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S IST"),
    }
    broker_state.setdefault("orders_placed_today", []).append(placed_entry)
    with open(state_file, "w", encoding="utf-8") as fh:
        json.dump(broker_state, fh, indent=2)

    print("Logged broker result: %s (Broker ID: %s)" % (args.status, args.broker_id))
    return 0


def run_fill(args):
    port_path = "trader/portfolio.json"
    portfolio = {"cash": 100000.0, "positions": []}
    if os.path.isfile(port_path):
        try:
            with open(port_path, encoding="utf-8") as fh:
                portfolio = json.load(fh)
        except Exception:
            pass

    sym = clean_symbol(args.symbol)
    side = args.side.lower()
    qty = args.qty
    price = args.price

    positions = portfolio.get("positions", [])
    found = False
    for p in positions:
        if clean_symbol(p.get("symbol")) == sym:
            found = True
            cur_qty = p.get("qty", 0)
            if side == "buy":
                new_qty = cur_qty + qty
                p["avg_price"] = round(((cur_qty * p.get("avg_price", price)) + (qty * price)) / new_qty, 2)
                p["qty"] = new_qty
            elif side == "sell":
                p["qty"] = max(0, cur_qty - qty)
            break

    if not found and side == "buy":
        positions.append({"symbol": sym, "qty": qty, "avg_price": price})

    portfolio["positions"] = [p for p in positions if p.get("qty", 0) > 0]
    os.makedirs("trader", exist_ok=True)
    with open(port_path, "w", encoding="utf-8") as fh:
        json.dump(portfolio, fh, indent=2)

    print("Updated portfolio: filled %s %d %s @ ₹%.2f" % (side.upper(), qty, sym, price))
    return 0


def run_flatten(args):
    sym = clean_symbol(args.symbol)
    qty = args.qty
    flatten_order = {
        "symbol": sym,
        "exchange": "NSE",
        "product": "MIS",
        "side": "sell",
        "qty": qty,
        "order_type": "market",
        "entry_price": 0.0,
        "time_in_force": "day",
        "order_class": "flatten_close",
    }
    out = {"orders": [flatten_order]}
    os.makedirs("trader", exist_ok=True)
    with open("trader/orders.json", "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2)
    print("Generated MIS Flatten Market Order: SELL %d %s (flat by close)" % (qty, sym))
    return 0


def run_log(args):
    if not os.path.isfile("trader/state/broker.json"):
        print("No execution decisions recorded today.")
        return 0
    with open("trader/state/broker.json", encoding="utf-8") as fh:
        data = json.load(fh)
    print("Broker Decision & Execution Log:")
    print(json.dumps(data, indent=2))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="Broker Order Execution Ticket Manager.")
    sub = parser.add_subparsers(dest="subcommand", required=True)

    # show
    p_s = sub.add_parser("show", help="Display order tickets")
    p_s.add_argument("--index", type=int, help="Single ticket index")
    p_s.add_argument("--now", help="Simulate clock")
    p_s.add_argument("--json", action="store_true")

    # approve
    p_a = sub.add_parser("approve", help="Explicitly approve an order")
    p_a.add_argument("--index", type=int, required=True)
    p_a.add_argument("--reply", required=True, help="User's explicit confirmation reply")

    # result
    p_r = sub.add_parser("result", help="Record broker placement result")
    p_r.add_argument("--index", type=int, required=True)
    p_r.add_argument("--status", required=True, choices=["placed", "failed", "denied"])
    p_r.add_argument("--broker-id", help="Broker order ID")

    # fill
    p_f = sub.add_parser("fill", help="Record execution fill in portfolio")
    p_f.add_argument("--symbol", required=True)
    p_f.add_argument("--side", required=True, choices=["buy", "sell"])
    p_f.add_argument("--qty", type=int, required=True)
    p_f.add_argument("--price", type=float, required=True)

    # flatten
    p_fl = sub.add_parser("flatten", help="Generate MIS square-off sell order")
    p_fl.add_argument("--symbol", required=True)
    p_fl.add_argument("--qty", type=int, required=True)

    # log
    p_l = sub.add_parser("log", help="Display today's order decisions log")

    args = parser.parse_args(argv)
    try:
        if args.subcommand == "show":
            return run_show(args)
        elif args.subcommand == "approve":
            return run_approve(args)
        elif args.subcommand == "result":
            return run_result(args)
        elif args.subcommand == "fill":
            return run_fill(args)
        elif args.subcommand == "flatten":
            return run_flatten(args)
        elif args.subcommand == "log":
            return run_log(args)
    except TicketError as err:
        print("error: %s" % err, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
