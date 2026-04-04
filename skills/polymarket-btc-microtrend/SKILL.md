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
