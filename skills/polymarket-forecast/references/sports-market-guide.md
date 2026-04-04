# Sports Market Guide

Use this reference when analyzing sports-related prediction markets.

## Scope

This guide is for lightweight forecasting of sports YES/NO markets such as:
- Will Team A beat Team B?
- Will Player X win this match?
- Will Team A qualify / advance / make playoffs?
- Will Player Y score / start / appear? (only if resolution wording is clear)
- Will Driver X finish ahead of Driver Y?
- Will Fighter X win the bout?

## Supported sport families in the bundled data

The skill currently ships heuristic priors for these sport families:
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

These map well to many Polymarket sports listings and aliases such as NFL, NBA, MLB, NHL, ATP, WTA, UFC, F1, IPL, CS2, Valorant, and Mobile Legends.

Run this command to inspect the live bundled catalog:

```bash
python scripts/market_bot.py list-sports
```

To pull a live Polymarket sports snapshot and auto-detect current sports markets:

```bash
python scripts/market_bot.py sync-live-sports --pages 3 --per-page 100 --include-unknown --output data/polymarket-sports-live.json
```

## Core sports inputs

For most sports, check these first:
- lineup / injury / suspension news
- home vs away context
- fatigue, travel, congestion, back-to-back schedule
- recent form
- matchup-specific style edges
- tournament format / rules / overtime / tie handling
- motivation and rotation risk
- weather / venue / surface / map pool where relevant

## Sport-family notes

### Soccer
Prioritize:
- expected starting XI
- rest and travel
- competition type (league, cup, knockout, two-leg tie)
- whether draw counts as NO or needs separate handling
- red-card volatility and lower-scoring variance

### American football
Prioritize:
- quarterback health and expected efficiency
- offensive line and secondary injuries
- weather and wind
- home field and travel
- rest differential

### Basketball
Prioritize:
- injury report / load management
- back-to-back games and travel
- pace and matchup fit
- home court
- playoff vs regular-season motivation

### Baseball
Prioritize:
- starting pitcher and bullpen freshness
- lineup confirmation
- park factor and weather
- platoon splits when relevant

### Hockey
Prioritize:
- starting goalie
- back-to-back fatigue
- special teams edge
- travel and home ice

### Tennis / badminton / table-tennis
Prioritize:
- surface or venue fit
- recent workload and fatigue
- health and retirement risk
- style matchup

### Cricket
Prioritize:
- format (T20, ODI, Test)
- toss and pitch conditions
- batting depth and bowling form
- weather interruptions

### Golf
Prioritize:
- course fit
- recent approach play / putting form
- weather
- whether the market is matchup-style or outright-style

### Formula 1 / motorsport
Prioritize:
- qualifying result
- car/team pace
- grid penalties
- weather and tire strategy
- reliability risk

### MMA / boxing
Prioritize:
- weight cut and short-notice replacements
- style matchup
- durability and recent damage
- age and activity level

### Rugby / volleyball / handball
Prioritize:
- squad selection
- travel and rest
- home advantage
- depth and physical mismatch

### Darts / snooker
Prioritize:
- recent form
- format length
- consistency floor vs ceiling
- fatigue and stage pressure

### Esports
Prioritize:
- roster stability
- patch or meta changes
- map pool
- LAN vs online environment
- recent opponent quality

## Confidence rules for sports

Use **low confidence** when:
- lineup or injury information is missing
- market wording is ambiguous
- last-minute volatility dominates
- your estimate depends on rumors

Use **high confidence** only when:
- resolution wording is clear
- team/player availability is known
- current form and matchup context align
- no major unknowns remain

## Sports bot usage

The bundled `scripts/market_bot.py` can generate a lightweight sports forecast using heuristic priors plus manual adjustments.

Example:

```bash
python scripts/market_bot.py sports \
  "Will Arsenal beat Chelsea?" \
  --sport soccer \
  --profile balanced_match \
  --favorite-status favorite \
  --home-advantage \
  --injury-impact -0.03 \
  --form-impact 0.04 \
  --implied-prob 0.57
```

Example with alias:

```bash
python scripts/market_bot.py sports \
  "Will Max Verstappen win the race?" \
  --sport f1 \
  --profile heavy_favorite \
  --favorite-status favorite \
  --form-impact 0.03 \
  --implied-prob 0.74
```

Use the bot as a starting point, then refine with fresh evidence and log the final forecast via `scripts/forecast_log.py`.

## Guardrails

Do not:
- claim certain wins
- ignore rule ambiguity
- treat a heuristic prior as a final answer
- mistake fan sentiment for evidence

Prefer disciplined updates over hot takes.