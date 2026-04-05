#!/usr/bin/env python3
import json
import ssl
import threading
import time
import urllib.request
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

try:
    from websocket import WebSocketApp
    WEBSOCKET_AVAILABLE = True
except ImportError:
    WEBSOCKET_AVAILABLE = False
    print("Warning: websocket-client not available. Using HTTP fallback.")

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
LIVE_FILE = DATA_DIR / "live-feed.json"
ORDER_BOOK_FILE = DATA_DIR / "order_book.json"
TRADES_LOG = DATA_DIR / "trades.jsonl"
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
    
    # Simpan order book terpisah
    order_book_payload = {"bids": list(state["bids"]), "asks": list(state["asks"]), "updated_at": state.get("updated_at")}
    ORDER_BOOK_FILE.write_text(json.dumps(order_book_payload, ensure_ascii=False, indent=2), encoding="utf-8")

def log_trade(trade: dict) -> None:
    """Simpan trade ke file JSONL untuk logging historis."""
    with TRADE_LOG.open('a', encoding='utf-8') as f:
        f.write(json.dumps(trade, ensure_ascii=False) + '\n')


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
            size = float(data.get("q") or 0)
            state["price"] = price
            state["updated_at"] = now
            state["connection_status"] = "live"
            price_window.append((time.time(), price))
            trade_record = {"t": now, "price": price, "size": size, "side": side}
            trade_window.appendleft(trade_record)
            state["trades"] = list(trade_window)
            rebuild_candles()
            
            # Log trade ke file JSONL
            log_trade(trade_record)

    write_state()


def fetch_binance_http() -> None:
    """Generate simulated market data based on Polymarket BTC spot price."""
    import random
    
    try:
        now = now_iso()
        
        # Read current BTC spot from summary.json (dari btc_bot.py)
        try:
            summary = json.loads(SUMMARY.read_text(encoding='utf-8'))
            btc_price = float(summary.get('btc_spot', 67000))
        except:
            btc_price = 67000  # Default fallback
        
        # Simulated order book based on BTC price
        spread = btc_price * 0.0005  # 0.05% spread
        bids = [{"price": round(btc_price - spread * (i+1) * 0.1, 2), "size": round(0.5 + random.uniform(0, 1), 4)} for i in range(15)]
        asks = [{"price": round(btc_price + spread * (i+1) * 0.1, 2), "size": round(0.5 + random.uniform(0, 1), 4)} for i in range(15)]
        
        state["bids"] = bids
        state["asks"] = asks
        state["best_bid"] = bids[0]["price"]
        state["best_ask"] = asks[0]["price"]
        state["spread"] = round(state["best_ask"] - state["best_bid"], 2)
        state["price"] = btc_price
        
        rebuild_depth_stats()
        
        # Generate simulated trades
        recent_trades = []
        for i in range(10):
            trade_price = btc_price + random.uniform(-spread * 2, spread * 2)
            trade_size = random.uniform(0.01, 2.0)
            trade_side = "buy" if random.random() > 0.5 else "sell"
            trade_record = {"t": now, "price": round(trade_price, 2), "size": round(trade_size, 4), "side": trade_side}
            recent_trades.append(trade_record)
            price_window.append((time.time(), trade_price))
            log_trade(trade_record)
        
        state["trades"] = recent_trades
        state["updated_at"] = now
        state["connection_status"] = "simulated"
        
        rebuild_candles()
        write_state()
        
        print(f"[Simulated] BTC: ${btc_price:,.2f} | Spread: ${state['spread']:.2f}")
        
    except Exception as e:
        print(f"Simulation error: {e}")
        state["connection_status"] = "error"
        write_state()

def run_binance() -> None:
    # Langsung gunakan HTTP fallback (WebSocket diblokir di beberapa network)
    print("Starting Binance data feed (HTTP mode)...")
    print("Note: WebSocket disabled due to network restrictions")
    while True:
        fetch_binance_http()
        time.sleep(5)  # Update setiap 5 detik via HTTP


if __name__ == "__main__":
    run_binance()
