#!/usr/bin/env python3
import json
import ssl
import threading
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

try:
    from websocket import WebSocketApp
except ImportError:
    raise SystemExit("Missing dependency: websocket-client. Install with: python -m pip install websocket-client")

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
LIVE_FILE = DATA_DIR / "live-feed.json"
DEPTH_LEVELS = 15

state = {
    "updated_at": None,
    "price": None,
    "best_bid": None,
    "best_ask": None,
    "spread": None,
    "bids": [],
    "asks": [],
    "trades": [],
    "candles": [],
    "candles_5m": [],
    "candles_15m": [],
    "connection_status": "connecting",
    "imbalance": None,
    "cum_bids": [],
    "cum_asks": [],
}
price_window = deque(maxlen=1800)
trade_window = deque(maxlen=50)
lock = threading.Lock()


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def rebuild_depth_stats() -> None:
    bids = state.get("bids") or []
    asks = state.get("asks") or []
    bid_total = sum(float(x.get("size") or 0) for x in bids)
    ask_total = sum(float(x.get("size") or 0) for x in asks)
    denom = bid_total + ask_total
    state["imbalance"] = round((bid_total - ask_total) / denom, 4) if denom else None

    cum = 0.0
    cum_bids = []
    for row in bids:
        cum += float(row.get("size") or 0)
        cum_bids.append({"price": row.get("price"), "size": row.get("size"), "cum": round(cum, 4)})
    cum = 0.0
    cum_asks = []
    for row in asks:
        cum += float(row.get("size") or 0)
        cum_asks.append({"price": row.get("price"), "size": row.get("size"), "cum": round(cum, 4)})
    state["cum_bids"] = cum_bids
    state["cum_asks"] = cum_asks


def write_state() -> None:
    with lock:
        payload = dict(state)
        payload["bids"] = list(state["bids"])
        payload["asks"] = list(state["asks"])
        payload["trades"] = list(state["trades"])
        payload["candles"] = list(state["candles"])
        payload["candles_5m"] = list(state.get("candles_5m") or [])
        payload["candles_15m"] = list(state.get("candles_15m") or [])
        payload["cum_bids"] = list(state.get("cum_bids") or [])
        payload["cum_asks"] = list(state.get("cum_asks") or [])
    LIVE_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def aggregate_candles(frame_seconds: int, limit: int = 60):
    buckets = {}
    for ts, price in list(price_window):
        bucket_ts = int(ts // frame_seconds) * frame_seconds
        bucket = buckets.setdefault(bucket_ts, {"t": bucket_ts, "o": price, "h": price, "l": price, "c": price})
        bucket["h"] = max(bucket["h"], price)
        bucket["l"] = min(bucket["l"], price)
        bucket["c"] = price
    return [buckets[k] for k in sorted(buckets.keys())][-limit:]


def rebuild_candles() -> None:
    state["candles"] = aggregate_candles(60, 60)
    state["candles_5m"] = aggregate_candles(300, 60)
    state["candles_15m"] = aggregate_candles(900, 60)


def on_combined_message(_ws, message: str) -> None:
    payload = json.loads(message)
    data = payload.get("data") or {}
    stream = payload.get("stream") or ""
    now = now_iso()

    with lock:
        if "@depth" in stream:
            bids = []
            asks = []
            for price, size in (data.get("b") or [])[:DEPTH_LEVELS]:
                bids.append({"price": float(price), "size": float(size)})
            for price, size in (data.get("a") or [])[:DEPTH_LEVELS]:
                asks.append({"price": float(price), "size": float(size)})
            state["bids"] = bids
            state["asks"] = asks
            rebuild_depth_stats()
            if bids:
                state["best_bid"] = bids[0]["price"]
            if asks:
                state["best_ask"] = asks[0]["price"]
            if state.get("best_bid") and state.get("best_ask"):
                state["spread"] = round(state["best_ask"] - state["best_bid"], 2)
            state["updated_at"] = now
            state["connection_status"] = "live"

        elif "@trade" in stream:
            price = float(data.get("p") or 0)
            side = "sell" if data.get("m") else "buy"
            state["price"] = price
            state["updated_at"] = now
            state["connection_status"] = "live"
            price_window.append((time.time(), price))
            trade_window.appendleft({"t": now, "price": price, "size": float(data.get("q") or 0), "side": side})
            state["trades"] = list(trade_window)
            rebuild_candles()

    write_state()


def run_binance() -> None:
    url = "wss://stream.binance.com:9443/stream?streams=btcusdt@depth20@100ms/btcusdt@trade"
    while True:
        state["connection_status"] = "connecting"
        write_state()
        ws = WebSocketApp(url, on_message=on_combined_message)
        ws.run_forever(sslopt={"cert_reqs": ssl.CERT_NONE}, ping_interval=20, ping_timeout=10)
        state["connection_status"] = "reconnecting"
        write_state()
        time.sleep(3)


if __name__ == "__main__":
    run_binance()
