"""
Day Trader Web Application & REST API Server.
Interactive 15m ORB Terminal with Intraday Candlestick Charting,
VWAP, Opening Range Boxes, and Time Machine Replay.
Standard library only (http.server, json, urllib).
"""

import sys
import os
import json
import urllib.parse
import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Dict, Any

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
ORDERS_FILE = os.path.join(ROOT_DIR, "trader", "orders.json")


def get_ist_now():
    # Return simulated or current IST time
    utc_now = datetime.datetime.now(datetime.timezone.utc)
    ist_now = utc_now + datetime.timedelta(hours=5, minutes=30)
    return ist_now


class DayTraderHandler(BaseHTTPRequestHandler):

    def _send_json(self, data: Any, status: int = 200):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode('utf-8'))

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        # 1. Static HTML Terminal
        if path == "/" or path == "/index.html":
            html_file = os.path.join(STATIC_DIR, "index.html")
            if os.path.exists(html_file):
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.end_headers()
                with open(html_file, 'rb') as f:
                    self.wfile.write(f.read())
                return
            else:
                self.send_error(404, "index.html not found")
                return

        # 2. REST API: /api/clock
        if path == "/api/clock":
            ist = get_ist_now()
            time_str = ist.strftime('%H:%M:%S')
            self._send_json({
                'ist_time': time_str,
                'session_open': '09:15',
                'or_end': '09:30',
                'prime_time_end': '10:15',
                'square_off': '15:15',
                'session_close': '15:30'
            })
            return

        # 3. REST API: /api/orders
        if path == "/api/orders":
            orders = []
            if os.path.exists(ORDERS_FILE):
                try:
                    with open(ORDERS_FILE, 'r') as f:
                        orders = json.load(f)
                except Exception:
                    pass
            self._send_json({'orders': orders})
            return

        # 4. REST API: /api/scan
        if path == "/api/scan":
            direction = query.get('direction', ['both'])[0]
            # Sample scan hits
            hits = [
                {
                    'symbol': 'RELIANCE',
                    'side': 'buy',
                    'direction': 'long',
                    'trigger_time': '09:45',
                    'entry_price': 2518.0,
                    'or_high': 2510.0,
                    'or_low': 2480.0,
                    'or_width_pct': 1.21,
                    'stop_loss': 2495.0,
                    'target1': 2564.0,
                    'vwap': 2505.37,
                    'rvol': 2.49,
                    'wick_pct': 28.6
                },
                {
                    'symbol': 'SBIN',
                    'side': 'sell',
                    'direction': 'short',
                    'trigger_time': '09:55',
                    'entry_price': 814.50,
                    'or_high': 829.50,
                    'or_low': 822.00,
                    'or_width_pct': 0.92,
                    'stop_loss': 822.00,
                    'target1': 799.50,
                    'vwap': 818.20,
                    'rvol': 1.85,
                    'wick_pct': 22.1
                }
            ]
            if direction == 'long':
                hits = [h for h in hits if h['direction'] == 'long']
            elif direction == 'short':
                hits = [h for h in hits if h['direction'] == 'short']
            self._send_json({'hits': hits, 'direction': direction})
            return

        self.send_error(404, "Not found")

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        content_len = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_len).decode('utf-8') if content_len > 0 else "{}"
        try:
            req_data = json.loads(body)
        except Exception:
            req_data = {}

        if path == "/api/order/submit":
            # Append to orders
            orders = []
            if os.path.exists(ORDERS_FILE):
                try:
                    with open(ORDERS_FILE, 'r') as f:
                        orders = json.load(f)
                except Exception:
                    pass
            orders.append(req_data)
            with open(ORDERS_FILE, 'w') as f:
                json.dump(orders, f, indent=2)
            self._send_json({'status': 'ok', 'message': f'Order placed for {req_data.get("symbol")}'})
            return

        self.send_error(404, "Not found")


def start_day_trader_server(port: int = 8502):
    server = HTTPServer(('0.0.0.0', port), DayTraderHandler)
    print(f"\n==================================================================")
    print(f"🚀 NSE Day Stock Analyser UI running at http://localhost:{port}")
    print(f"   • Interactive 5m/15m Candlestick Chart View with Opening Range (OR) Box")
    print(f"   • Dynamic VWAP Line, OR-Mid Stop Reference, and 2R/3R Target Lines")
    print(f"   • Bi-Directional ORB Scanner (Long Breakouts & Short Breakdowns)")
    print(f"   • Bracket Order Paper Broker with +1.2R Breakeven Trailing Stop")
    print(f"   • Time Machine Historical Replay Simulator")
    print(f"==================================================================\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Day Trader UI server...")
        server.server_close()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Start Day Stock Analyser UI Server.")
    parser.add_argument("--port", type=int, default=8502, help="Port to listen on (default: 8502)")
    args = parser.parse_args()
    start_day_trader_server(port=args.port)
