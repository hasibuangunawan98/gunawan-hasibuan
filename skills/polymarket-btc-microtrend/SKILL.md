---
name: polymarket-btc-microtrend
description: Scan Polymarket Bitcoin markets using short-term 5m and 15m crypto microtrend logic with real-time public market data and Chainlink price anchoring. Use when building or running a BTC-focused signal bot, microtrend dashboard, black-swan filter, paper-trading workflow, or market scanner for live Polymarket crypto markets.
---

# Polymarket BTC Microtrend

Use this skill to build and run a short-term Bitcoin signal bot for Polymarket.

## What this skill does

- fetch live Polymarket markets relevant to BTC
- fetch real-time BTC price data from public exchange endpoints
- fetch a Chainlink BTC/USD anchor feed snapshot
- compute 5m and 15m signal states
- apply black-swan / event-risk guards
- produce a ranked signal list
- render a modern HTML dashboard
- support paper-trading style workflows and logging

## Main scripts

- `scripts/btc_bot.py`

## Main modes

- `scan-btc`
- `auto-btc`

## Notes

This skill is intended as a signal engine and dashboard first.
Use it to decide when a setup looks strong, weak, or not tradable.

When deeper rule changes are needed, update:
- `references/strategy.md`
- `scripts/btc_bot.py`

## Quick Start

### 1. Install Dependencies

```bash
python -m pip install websocket-client
```

### 2. Run Real-Time Data Feed (Background)

Start the WebSocket bridge to fetch real-time order book and trades from Binance:

```bash
python scripts/btc_ws_bridge.py
```

This will create:
- `data/live-feed.json` - Full real-time state
- `data/order_book.json` - Order book snapshot
- `data/trades.jsonl` - Trade history log

### 3. Run BTC Signal Bot

In another terminal, run the signal bot:

```bash
python scripts/btc_bot.py scan-btc
```

Or for auto mode with dashboard generation:

```bash
python scripts/btc_bot.py auto-btc
```

### 4. Open Dashboard

Open `data/dashboard.html` in your browser. It will auto-refresh every 10 seconds.

## Real-Time Features

- **Order Book**: Top 10 bid/ask levels with size
- **Recent Trades**: Last 10 trades with price, size, and side
- **Price Chart**: Real-time BTC price chart using Chart.js
- **WebSocket Feed**: Live connection to Binance for order book and trades

## Data Files

| File | Description |
|------|-------------|
| `data/live-feed.json` | Full real-time state (price, candles, order book, trades) |
| `data/order_book.json` | Order book snapshot for dashboard |
| `data/trades.jsonl` | Historical trade log (JSONL format) |
| `data/dashboard.html` | Interactive dashboard with real-time data |
| `data/summary.json` | Signal analysis summary |
| `data/signals.jsonl` | Signal history log |
