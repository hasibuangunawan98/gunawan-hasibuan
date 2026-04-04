---
name: polymarket-forecast
description: Analyze Polymarket and other prediction-market questions with structured research, probability estimation, confidence scoring, automation-ready logging, and backtesting discipline. Use when asked to evaluate a market, estimate YES/NO odds, compare implied market price vs estimated probability, summarize bullish/bearish cases, identify weakly specified markets, design a prediction bot workflow, maintain a forecast log for later calibration review, or build lightweight sports-market analysis using heuristic priors plus current evidence. Do not use this skill to promise guaranteed profits or fixed win rates.
---

# Polymarket Forecast

Estimate prediction-market probabilities with explicit uncertainty, not hype.

## Workflow

1. Restate the market precisely.
2. Extract the resolution criteria and time horizon.
3. Gather fresh evidence.
4. Separate base rates from current catalysts.
5. Estimate a probability range, then choose a point estimate.
6. Compare the estimate to current market pricing.
7. Report confidence, risks, and invalidation triggers.
8. Log the forecast so it can be backtested later.

## 1) Restate the market precisely

Before forecasting, rewrite the market in plain language:
- What exactly must happen for **YES** to resolve?
- What counts as **NO**?
- What source decides resolution?
- What is the deadline?
- Are there ambiguous terms that make the market dangerous?

If the wording is vague, say so clearly and lower confidence.

## 2) Build the research set

Use current, sourceable information. Prefer primary or near-primary sources when available.

Prioritize evidence in this order:
1. Official documents, court filings, regulator posts, exchange notices, company releases
2. Direct statements from named participants or institutions
3. Reputable reporting with named sourcing
4. Historical/base-rate data
5. Market chatter or social posts only as weak supporting evidence

Do not treat a viral claim as strong evidence without confirmation.

## 3) Decompose the forecast

Break the market into drivers such as:
- legal or regulatory outcome
- election or political dynamics
- product launch or company action
- timing risk
- liquidity and execution constraints
- information asymmetry
- wording / resolution ambiguity
- sport-specific inputs such as lineup, injuries, home advantage, fatigue, or surface

When useful, convert the market into conditional pieces:
- Probability event A happens
- Probability event B follows if A happens
- Final probability = combined estimate

Use rough math when it improves clarity.

## 4) Estimate probability

Start with a base rate, then adjust.

Practical method:
- Set an initial range from history or comparable cases
- Add or subtract for current evidence
- Narrow to a final point estimate only after checking whether the evidence quality justifies precision

Avoid fake precision. Prefer:
- "Estimated probability: 62%"
- over "62.37%"

If evidence is weak, use a wider range and say confidence is low.

## 5) Compare to market price

If the current market price is available, convert it to implied probability and compare it to your estimate.

Classify the setup as:
- **No edge**: estimate roughly matches price
- **Possible edge**: estimate differs modestly but evidence is mixed
- **Strong candidate mispricing**: estimate differs materially and evidence quality is strong

Do not say "buy" or "guaranteed profit." Frame it as a research view, not certainty.

## 6) Always report uncertainty

Every forecast must include:
- point estimate
- confidence level: low / medium / high
- strongest evidence for YES
- strongest evidence for NO
- key unknowns
- what new information would change the estimate

If the market is not forecastable with current information, say that directly.

## 7) Log and backtest

Use the bundled script `scripts/forecast_log.py` to maintain a JSONL forecast log.

Track at least:
- timestamp
- market ID or URL
- market text
- estimated YES probability
- implied market probability at forecast time
- confidence
- rationale
- final outcome after resolution

Review Brier score and calibration over time. Win rate alone is not enough.

## 8) Sports mode

For sports-related markets, use the bundled `scripts/market_bot.py` and the `assets/sports-priors.json` heuristic base data as a starting point. The script also supports live Polymarket discovery, so it can fetch active events, auto-detect likely sports markets, and save a local snapshot for review.

Supported sports priors currently cover a broad Polymarket-style catalog, including:
- american-football
- basketball
- baseball
- hockey
- soccer
- tennis
- cricket
- golf
- formula-1
- motorsport
- mma
- boxing
- rugby
- badminton
- volleyball
- table-tennis
- handball
- darts
- cycling
- snooker
- esports

Run `python scripts/market_bot.py list-sports` to inspect the bundled catalog and aliases.

Treat these priors as lightweight starting points only. Always adjust for live information such as lineup news, injuries, suspension, schedule, travel, motivation, surface, weather, map pool, or rule-specific resolution details.

## 9) Guardrails

Do not:
- promise 90% accuracy
- promise profit
- present uncertain claims as facts
- ignore contradictory evidence
- confuse market price with truth

Prefer honest uncertainty over confident nonsense.

## Output format

Use this structure when answering:

### Market
- Restated market: ...
- Resolution source/deadline: ...

### Estimate
- YES probability: ...
- NO probability: ...
- Confidence: low / medium / high

### Why YES
- ...
- ...

### Why NO
- ...
- ...

### Pricing check
- Current market implied probability: ...
- Difference vs estimate: ...
- View: no edge / possible edge / candidate mispricing

### Risks / unknowns
- ...
- ...

### What would change the forecast
- ...
- ...

## Bundled resources

### `scripts/forecast_log.py`
Use for lightweight logging, resolving, and backtesting forecast entries.

Supported commands:
- `add`
- `resolve`
- `show`
- `stats`

### `scripts/market_bot.py`
Use for lightweight CLI analysis scaffolding, especially for sports markets.

Current modes:
- `list-sports`
- `sports`
- `sync-live-sports`
- `inspect-live-market`
- `auto-forecast-live`
- `rank-live-markets`
- `auto-cycle`
- `find-live-locks`
- `auto-live-locks`

### `references/forecast-rubric.md`
Read when you need a reusable evidence-scoring rubric, confidence checklist, or backtesting template.

### `references/automation-workflow.md`
Read when you need to turn this skill into a lightweight prediction bot workflow or recurring forecast process.

### `references/sports-market-guide.md`
Read when analyzing sports prediction markets or deciding how to adjust sports priors.

### `references/live-polymarket-sync.md`
Read when you need live Polymarket sports discovery, snapshot syncing, single-market inspection by slug/URL, or an initial heuristic auto-forecast from a live Polymarket market.

### `assets/sports-priors.json`
Use as heuristic base-rate data for sports-related markets. Do not treat it as a guaranteed edge or a replacement for fresh evidence.