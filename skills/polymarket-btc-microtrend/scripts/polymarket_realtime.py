#!/usr/bin/env python3
import json
import time
import websocket
import threading
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from typing import Any, Dict, List, Optional, Callable

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / 'data'
SUMMARY = DATA / 'summary.json'
OUT = DATA / 'polymarket-live.json'
ORDER_BOOK = DATA / 'order_book.json'
HEADERS = {'User-Agent': 'Mozilla/5.0 (compatible; polymarket-realtime/1.0)', 'Accept': 'application/json'}
POLYMARKET_WS_URL = "wss://gamma-api.polymarket.com/ws"


def now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_json(path: Path, fallback):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return fallback


def fetch_json(url: str) -> Any:
    req = Request(url, headers=HEADERS)
    with urlopen(req, timeout=20) as resp:
        return json.load(resp)

def on_message(ws, message: str, callback: Optional[Callable] = None):
    data = json.loads(message)
    if callback:
        callback(data)

def on_error(ws, error):
    print(f"WebSocket Error: {error}")

def on_close(ws, close_status_code, close_msg):
    print("WebSocket Closed")

def on_open(ws):
    print("WebSocket Connected")
    # Subscribe ke channel order book dan trades
    subscribe_message = {
        "action": "subscribe",
        "channels": ["order_book", "trades"],
        "market": "BTC"
    }
    ws.send(json.dumps(subscribe_message))

def start_websocket(callback: Callable):
    ws = websocket.WebSocketApp(
        POLYMARKET_WS_URL,
        on_open=on_open,
        on_message=lambda ws, msg: on_message(ws, msg, callback),
        on_error=on_error,
        on_close=on_close
    )
    wst = threading.Thread(target=ws.run_forever)
    wst.daemon = True
    wst.start()
    return ws


def safe_float(v):
    try:
        return float(v)
    except Exception:
        return None


def extract_live(summary):
    best = summary.get('best_setup') or {}
    signals = summary.get('signals') or []
    top = [s for s in signals[:8] if s.get('url')]
    items = []
    for s in top:
        items.append({
            'question': s.get('question'),
            'url': s.get('url'),
            'implied_yes_probability': s.get('implied_yes_probability'),
            'action': s.get('action'),
            'bias': s.get('bias'),
            'confidence': s.get('confidence'),
            'model_score': s.get('model_score'),
            'resolution_source': s.get('resolution_source') or {},
        })
    return {'best': best, 'items': items}


def build_payload(prev):
    summary = load_json(SUMMARY, {})
    live = extract_live(summary)
    deltas = []
    prev_map = {x.get('question'): x for x in (prev.get('items') or [])}
    for item in live['items']:
        q = item.get('question')
        old = prev_map.get(q, {})
        new_p = safe_float(item.get('implied_yes_probability'))
        old_p = safe_float(old.get('implied_yes_probability'))
        delta = None if new_p is None or old_p is None else round(new_p - old_p, 4)
        item['delta_probability'] = delta
        if delta is not None and abs(delta) >= 0.03:
            deltas.append({'question': q, 'delta_probability': delta, 'new_probability': new_p})
    return {
        'updated_at': now_iso(),
        'status': 'live-ish',
        'best': live['best'],
        'items': live['items'],
        'significant_moves': deltas,
    }


def handle_websocket_data(data: Dict):
    """Callback untuk menangani data dari WebSocket."""
    if data.get("channel") == "order_book":
        ORDER_BOOK.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    elif data.get("channel") == "trades":
        print(f"New Trade: {data}")

def main():
    DATA.mkdir(parents=True, exist_ok=True)
    prev = load_json(OUT, {})
    
    # Mulai WebSocket untuk data real-time
    start_websocket(handle_websocket_data)
    
    while True:
        try:
            payload = build_payload(prev)
            OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
            prev = payload
        except Exception as e:
            print(f"Error: {e}")
        time.sleep(5)


if __name__ == '__main__':
    main()
