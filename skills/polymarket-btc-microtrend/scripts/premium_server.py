#!/usr/bin/env python3
import json
import threading
import time
import webbrowser
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
HOST = '127.0.0.1'
PORT = 8765

ASSETS = ROOT / 'assets'
DATA = ROOT / 'data'
LIVE = DATA / 'live-feed.json'
SUMMARY = DATA / 'summary.json'
STATE = DATA / 'premium-state.json'

for p in [DATA, ASSETS]:
    p.mkdir(parents=True, exist_ok=True)


def load_json(path: Path, fallback):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return fallback


def save_state(payload):
    STATE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')


def compute_alerts(live, summary):
    alerts = []
    imbalance = live.get('imbalance')
    conn = live.get('connection_status')
    best = summary.get('best_setup') or {}
    if conn in {'reconnecting', 'connecting'}:
        alerts.append({'level': 'warn', 'title': 'Feed status', 'message': f'Connection is {conn}.'})
    if imbalance is not None and abs(float(imbalance)) >= 0.2:
        side = 'buyers' if imbalance > 0 else 'sellers'
        alerts.append({'level': 'info', 'title': 'Depth imbalance', 'message': f'{side.capitalize()} dominating order book ({imbalance:.2%}).'})
    action = str(best.get('action') or '')
    if action and 'watch' in action:
        alerts.append({'level': 'good', 'title': 'Polymarket watch', 'message': f"{best.get('question','Signal')} -> {action}"})
    elif action and ('skip' in action or 'avoid' in action):
        alerts.append({'level': 'warn', 'title': 'Polymarket caution', 'message': f"{best.get('question','Signal')} -> {action}"})
    return alerts


def build_heatmap(live):
    bids = live.get('cum_bids') or []
    asks = live.get('cum_asks') or []
    max_cum = max([1.0] + [float(x.get('cum') or 0) for x in bids + asks])
    rows = []
    for row in reversed(bids[-12:]):
        rows.append({'side': 'bid', 'price': row.get('price'), 'size': row.get('size'), 'cum': row.get('cum'), 'intensity': round(float(row.get('cum') or 0) / max_cum, 4)})
    for row in asks[:12]:
        rows.append({'side': 'ask', 'price': row.get('price'), 'size': row.get('size'), 'cum': row.get('cum'), 'intensity': round(float(row.get('cum') or 0) / max_cum, 4)})
    return rows


def build_state():
    live = load_json(LIVE, {})
    summary = load_json(SUMMARY, {})
    signals = summary.get('signals') or []
    best = summary.get('best_setup')
    if not best and signals:
        best = sorted(signals, key=lambda x: float(x.get('model_score') or 0), reverse=True)[0]
    payload = {
        'generated_at': time.time(),
        'live': live,
        'summary': {
            'ran_at': summary.get('ran_at'),
            'btc_spot': summary.get('btc_spot'),
            'regime': summary.get('regime'),
            'black_swan_status': summary.get('black_swan_status'),
            'best_setup': best,
            'top_signals': signals[:6],
        },
        'heatmap': build_heatmap(live),
    }
    payload['alerts'] = compute_alerts(live, payload['summary'])
    save_state(payload)


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def log_message(self, format, *args):
        return

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path in {'/', '/premium'}:
            self.path = '/assets/premium_dashboard_v2.html'
        elif parsed.path == '/api/state':
            build_state()
            data = STATE.read_text(encoding='utf-8') if STATE.exists() else '{}'
            body = data.encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        return super().do_GET()


def updater():
    while True:
        try:
            build_state()
        except Exception:
            pass
        time.sleep(1)


def main():
    threading.Thread(target=updater, daemon=True).start()
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    webbrowser.open(f'http://{HOST}:{PORT}/premium')
    print(f'Premium cockpit running at http://{HOST}:{PORT}/premium')
    server.serve_forever()


if __name__ == '__main__':
    main()
