# BTC Microtrend Strategy

## Goal

Find high-quality BTC setups for Polymarket using:
- Polymarket live market pricing
- exchange spot price action
- Chainlink BTC/USD anchor snapshot
- volatility and black-swan filters
- distance-to-target and time-to-deadline logic

## Market styles

- short-term microtrend markets, if available
- level target markets
- deadline-based BTC hit / above / below markets

## Core signals

### Trend alignment
- price vs EMA-9
- EMA-9 vs EMA-20
- short-term return
- distance from VWAP proxy

### Momentum
- latest candle direction
- 5m and 15m change
- acceleration

### Volatility guards
- recent range too large
- abnormal jump vs baseline
- exchange-anchor divergence

### Distance-to-target / deadline logic
- current BTC spot vs target level
- percent distance to target
- deadline proximity inferred from market text where possible
- implied market probability vs simple distance heuristic

### Black-swan guards
- sudden move spike
- exchange disagreement
- excessive 24h volatility
- missing market consensus

## Output states

- `strong-bullish`
- `bullish`
- `neutral`
- `bearish`
- `strong-bearish`
- `level-watch`
- `no-trade`

## Practical guidance

Prefer `no-trade` over forcing a signal.
If black-swan risk triggers, suppress aggressive calls.
If Polymarket price is already too efficient, downgrade confidence.
