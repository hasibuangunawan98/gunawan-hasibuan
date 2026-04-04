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
POLY_LIVE = DATA / 'polymarket-live.json'
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


def infer_tape_bias(live):
    trades = live.get('trades') or []
    if not trades:
        return {'buy_volume': 0.0, 'sell_volume': 0.0, 'delta': 0.0, 'bias': 'neutral'}
    buy_volume = sum(float(t.get('size') or 0) for t in trades if t.get('side') == 'buy')
    sell_volume = sum(float(t.get('size') or 0) for t in trades if t.get('side') == 'sell')
    delta = buy_volume - sell_volume
    if delta > 0:
        bias = 'bullish'
    elif delta < 0:
        bias = 'bearish'
    else:
        bias = 'neutral'
    return {'buy_volume': round(buy_volume, 4), 'sell_volume': round(sell_volume, 4), 'delta': round(delta, 4), 'bias': bias}


def infer_mtf_bias(live):
    out = {}
    for key, label in [('candles', '1m'), ('candles_5m', '5m'), ('candles_15m', '15m')]:
        rows = live.get(key) or []
        if len(rows) >= 2:
            first = float(rows[0].get('o') or rows[0].get('c') or 0)
            last = float(rows[-1].get('c') or 0)
            change = ((last - first) / first) if first else 0.0
            bias = 'bullish' if change > 0.001 else ('bearish' if change < -0.001 else 'neutral')
            out[label] = {'change': round(change, 4), 'bias': bias}
        else:
            out[label] = {'change': 0.0, 'bias': 'neutral'}
    return out


def build_fusion(live, summary):
    best = summary.get('best_setup') or {}
    imbalance = live.get('imbalance')
    tape = infer_tape_bias(live)
    mtf = infer_mtf_bias(live)
    score = 0
    reasons = []
    if imbalance is not None:
        if float(imbalance) > 0.08:
            score += 1
            reasons.append('bid depth stronger')
        elif float(imbalance) < -0.08:
            score -= 1
            reasons.append('ask depth stronger')
    if tape['bias'] == 'bullish':
        score += 1
        reasons.append('buy tape stronger')
    elif tape['bias'] == 'bearish':
        score -= 1
        reasons.append('sell tape stronger')
    for tf in ['1m', '5m', '15m']:
        if mtf[tf]['bias'] == 'bullish':
            score += 1
        elif mtf[tf]['bias'] == 'bearish':
            score -= 1
    pm_bias = str(best.get('bias') or '')
    if 'bull' in pm_bias:
        score += 2
        reasons.append('Polymarket bias bullish')
    elif 'bear' in pm_bias:
        score -= 2
        reasons.append('Polymarket bias bearish')
    stance = 'bullish' if score >= 3 else ('bearish' if score <= -3 else 'neutral')
    confidence = 'high' if abs(score) >= 5 else ('medium' if abs(score) >= 3 else 'low')
    action = 'watch-long' if stance == 'bullish' else ('watch-short' if stance == 'bearish' else 'wait')
    return {
        'score': score,
        'stance': stance,
        'confidence': confidence,
        'action': action,
        'reasons': reasons,
        'tape': tape,
        'mtf': mtf,
    }


def build_action_layer(live, fusion, poly_live):
    score = int(fusion.get('score') or 0)
    spread = float(live.get('spread') or 0)
    imbalance = float(live.get('imbalance') or 0) if live.get('imbalance') is not None else 0.0
    moves = poly_live.get('significant_moves') or []
    move_bias = 'neutral'
    if moves:
        delta = float(moves[0].get('delta_probability') or 0)
        move_bias = 'bullish' if delta > 0 else ('bearish' if delta < 0 else 'neutral')
        score += 1 if delta > 0 else (-1 if delta < 0 else 0)
    if spread >= 5:
        score = 0
        decision = 'no-trade'
        conviction = 'high'
        reason = 'spread too wide'
    elif score >= 6 and imbalance > 0:
        decision = 'strong-long-watch'
        conviction = 'high'
        reason = 'fusion aligned strongly bullish'
    elif score >= 3:
        decision = 'weak-long-watch'
        conviction = 'medium'
        reason = 'bullish bias but not extreme'
    elif score <= -6 and imbalance < 0:
        decision = 'strong-short-watch'
        conviction = 'high'
        reason = 'fusion aligned strongly bearish'
    elif score <= -3:
        decision = 'weak-short-watch'
        conviction = 'medium'
        reason = 'bearish bias but not extreme'
    else:
        decision = 'no-trade'
        conviction = 'low'
        reason = 'mixed signals'
    return {
        'decision': decision,
        'conviction': conviction,
        'reason': reason,
        'score_after_polymarket': score,
        'spread': spread,
        'imbalance': round(imbalance, 4),
        'polymarket_move_bias': move_bias,
    }


def compute_alerts(live, summary, fusion):
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
    if fusion.get('confidence') in {'medium', 'high'} and fusion.get('stance') != 'neutral':
        alerts.append({'level': 'good' if fusion.get('stance') == 'bullish' else 'warn', 'title': 'Fusion signal', 'message': f"{fusion.get('action')} · score {fusion.get('score')} · {', '.join(fusion.get('reasons')[:3])}"})
    spread = live.get('spread')
    if spread is not None and float(spread) >= 3:
        alerts.append({'level': 'warn', 'title': 'Spread expansion', 'message': f'Spread widened to {spread}.'})
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
    poly_live = load_json(POLY_LIVE, {})
    signals = summary.get('signals') or []
    best = summary.get('best_setup')
    if not best and signals:
        best = sorted(signals, key=lambda x: float(x.get('model_score') or 0), reverse=True)[0]
    fusion = build_fusion(live, {'best_setup': best})
    action_layer = build_action_layer(live, fusion, poly_live)
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
        'polymarket_live': poly_live,
        'resolution_audit': {
            'best_source': (best.get('resolution_source') or {}),
            'top_sources': [((s.get('resolution_source') or {}).get('source_type') or 'unspecified') for s in signals[:6]],
        },
        'heatmap': build_heatmap(live),
        'fusion': fusion,
        'action_layer': action_layer,
    }
    payload['alerts'] = compute_alerts(live, payload['summary'], fusion)
    if (poly_live.get('significant_moves') or []):
        move = poly_live['significant_moves'][0]
        payload['alerts'].append({'level': 'info', 'title': 'Polymarket move', 'message': f"{move.get('question','Market')} moved {move.get('delta_probability')}"})
    payload['alerts'].append({'level': 'good' if 'long' in action_layer.get('decision','') else ('warn' if 'short' in action_layer.get('decision','') else 'info'), 'title': 'Bot action layer', 'message': f"{action_layer.get('decision')} · conviction {action_layer.get('conviction')} · {action_layer.get('reason')}"})
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
