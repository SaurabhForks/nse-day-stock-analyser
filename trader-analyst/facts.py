#!/usr/bin/env python3
"""Earnings & Ind-AS Financial Analyst for Indian Companies. Standard library only.

    python3 facts.py RELIANCE
    python3 facts.py TCS INFY --quarters 8
    python3 facts.py RELIANCE --json
    python3 facts.py RELIANCE TCS HDFCBANK --metrics trader/metrics.json

Extracts and analyzes quarterly results (Q1, Q2, Q3, Q4) and Annual Reports under
Indian Accounting Standards (Ind-AS). Displays revenue, EBITDA, PAT (Profit After Tax),
margins, and diluted EPS in ₹ Crores (Cr) and ₹ Lakhs (L). Never recommends buying.
"""

import argparse
import datetime as _dt
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
YAHOO_HOSTS = ("query2.finance.yahoo.com", "query1.finance.yahoo.com")


class FactsError(Exception):
    pass


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


def to_crores(val):
    """Convert raw INR amount to Crores (1 Cr = 10,000,000 INR)."""
    if val is None:
        return 0.0
    return round(float(val) / 10000000.0, 2)


def format_inr_crores(val_cr):
    """Format float into '₹ X,XXX.XX Cr'."""
    return "₹{:,.2f} Cr".format(val_cr)


def fetch_financials(symbol, offline=None):
    sym = clean_symbol(symbol)
    if offline:
        path = offline
        if os.path.isdir(path):
            cand = os.path.join(path, "financials-%s.json" % sym)
            if not os.path.isfile(cand):
                cand = os.path.join(path, "%s.json" % sym)
            if not os.path.isfile(cand):
                cand = os.path.join(path, "%s.NS.json" % sym)
            if os.path.isfile(cand):
                path = cand
        if os.path.isfile(path):
            opener = gzip.open if path.endswith(".gz") else open
            with opener(path, "rt", encoding="utf-8") as fh:
                return json.load(fh)
        raise FactsError("offline financials file not found: %s" % path)

    y_sym = yahoo_symbol(sym)
    url = "https://%s/v10/finance/quoteSummary/%s?modules=incomeStatementHistory,incomeStatementHistoryQuarterly,financialData,defaultKeyStatistics" % (
        YAHOO_HOSTS[0], y_sym
    )
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
    try:
        with urllib.request.urlopen(req, timeout=12, context=SSL_CTX) as resp:
            data = resp.read()
            if resp.info().get("Content-Encoding") == "gzip":
                data = gzip.decompress(data)
            return json.loads(data.decode("utf-8"))
    except Exception as exc:
        raise FactsError("failed to fetch financials for %s: %s" % (sym, exc))


def parse_quarters(data):
    """Extract quarterly income statement rows."""
    res = data.get("quoteSummary", {}).get("result", [{}])[0]
    q_stmts = res.get("incomeStatementHistoryQuarterly", {}).get("incomeStatementHistory", [])

    quarters = []
    for stmt in q_stmts:
        end_date = stmt.get("endDate", {}).get("fmt") or "--"
        rev = stmt.get("totalRevenue", {}).get("raw")
        ebitda = stmt.get("ebitda", {}).get("raw") or stmt.get("operatingIncome", {}).get("raw")
        net_inc = stmt.get("netIncome", {}).get("raw") or stmt.get("netIncomeApplicableToCommonShares", {}).get("raw")
        eps = stmt.get("dilutedEPS", {}).get("raw")

        rev_cr = to_crores(rev)
        ebitda_cr = to_crores(ebitda)
        net_inc_cr = to_crores(net_inc)

        ebitda_margin = round((ebitda / rev * 100.0), 2) if rev and ebitda else 0.0
        pat_margin = round((net_inc / rev * 100.0), 2) if rev and net_inc else 0.0

        quarters.append({
            "end_date": end_date,
            "revenue_cr": rev_cr,
            "ebitda_cr": ebitda_cr,
            "pat_cr": net_inc_cr,
            "ebitda_margin_pct": ebitda_margin,
            "pat_margin_pct": pat_margin,
            "eps_diluted": float(eps) if eps is not None else 0.0,
        })

    # Sort chronological
    quarters.sort(key=lambda x: x["end_date"])

    # Calculate QoQ and YoY
    for i in range(len(quarters)):
        if i > 0 and quarters[i - 1]["revenue_cr"] > 0:
            qoq = ((quarters[i]["revenue_cr"] - quarters[i - 1]["revenue_cr"]) / quarters[i - 1]["revenue_cr"]) * 100.0
            quarters[i]["revenue_qoq_pct"] = round(qoq, 1)
        else:
            quarters[i]["revenue_qoq_pct"] = None

        if i >= 4 and quarters[i - 4]["revenue_cr"] > 0:
            yoy = ((quarters[i]["revenue_cr"] - quarters[i - 4]["revenue_cr"]) / quarters[i - 4]["revenue_cr"]) * 100.0
            quarters[i]["revenue_yoy_pct"] = round(yoy, 1)
        else:
            quarters[i]["revenue_yoy_pct"] = None

    return quarters


def analyze_company(symbol, offline=None, num_quarters=4):
    sym = clean_symbol(symbol)
    raw = fetch_financials(sym, offline=offline)
    quarters = parse_quarters(raw)
    recent_q = quarters[-num_quarters:] if quarters else []

    # Calculate TTM (Trailing Twelve Months)
    ttm_rev = sum(q["revenue_cr"] for q in recent_q[-4:]) if len(recent_q) >= 4 else 0.0
    ttm_pat = sum(q["pat_cr"] for q in recent_q[-4:]) if len(recent_q) >= 4 else 0.0
    ttm_eps = sum(q["eps_diluted"] for q in recent_q[-4:]) if len(recent_q) >= 4 else 0.0

    return {
        "symbol": sym,
        "quarters": recent_q,
        "ttm": {
            "revenue_cr": round(ttm_rev, 2),
            "pat_cr": round(ttm_pat, 2),
            "eps": round(ttm_eps, 2),
            "net_margin_pct": round((ttm_pat / ttm_rev * 100.0), 2) if ttm_rev > 0 else 0.0,
        },
    }


def run_facts(args):
    symbols = [clean_symbol(s) for s in args.symbols]
    if not symbols:
        symbols = ["RELIANCE"]

    results = []
    metrics_rows = {}

    for sym in symbols:
        try:
            res = analyze_company(sym, offline=args.offline, num_quarters=args.quarters)
            results.append(res)
            metrics_rows[sym] = {
                "ttm_revenue_cr": res["ttm"]["revenue_cr"],
                "ttm_pat_cr": res["ttm"]["pat_cr"],
                "ttm_eps": res["ttm"]["eps"],
                "net_margin_pct": res["ttm"]["net_margin_pct"],
                "latest_quarter": res["quarters"][-1] if res["quarters"] else None,
            }
        except Exception as e:
            print("Facts error for %s: %s" % (sym, e), file=sys.stderr)

    if args.metrics:
        os.makedirs(os.path.dirname(os.path.abspath(args.metrics)), exist_ok=True)
        with open(args.metrics, "w", encoding="utf-8") as fh:
            json.dump(metrics_rows, fh, indent=2)
        print("Wrote metrics to %s" % args.metrics)

    if args.json:
        print(json.dumps(results, indent=2))
        return 0

    for r in results:
        print("=" * 65)
        print("Financial Analysis for %s (Ind-AS Reporting):" % r["symbol"])
        print("TTM Revenue: ₹%.2f Cr | TTM PAT: ₹%.2f Cr | TTM EPS: ₹%.2f | Net Margin: %.2f%%" % (
            r["ttm"]["revenue_cr"], r["ttm"]["pat_cr"], r["ttm"]["eps"], r["ttm"]["net_margin_pct"]
        ))
        print("-" * 65)
        print("Quarterly Performance (₹ Crores):")
        print("%-12s | %-12s | %-12s | %-10s | %-8s | %-8s" % (
            "Quarter End", "Revenue", "EBITDA (Margin)", "PAT (Margin)", "EPS", "YoY Growth"
        ))
        print("-" * 65)
        for q in r["quarters"]:
            yoy_str = ("%+.1f%%" % q["revenue_yoy_pct"]) if q.get("revenue_yoy_pct") is not None else "--"
            print("%-12s | ₹%-10.2f | ₹%-7.2f (%4.1f%%) | ₹%-6.2f (%4.1f%%) | ₹%-6.2f | %s" % (
                q["end_date"], q["revenue_cr"], q["ebitda_cr"], q["ebitda_margin_pct"],
                q["pat_cr"], q["pat_margin_pct"], q["eps_diluted"], yoy_str
            ))

    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="Ind-AS Earnings & Financial Analyst for Indian Equities.")
    parser.add_argument("symbols", nargs="+", help="Company symbols (e.g. RELIANCE TCS)")
    parser.add_argument("--quarters", type=int, default=4, help="Number of quarters to display (default 4)")
    parser.add_argument("--offline", help="Path to offline financials JSON or folder")
    parser.add_argument("--metrics", help="Save TTM metrics to JSON file")
    parser.add_argument("--json", action="store_true", help="Output JSON only")

    args = parser.parse_args(argv)
    try:
        return run_facts(args)
    except FactsError as err:
        print("error: %s" % err, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
