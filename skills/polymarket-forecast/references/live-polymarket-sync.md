# Live Polymarket Sync

Use this reference when you need live-ish Polymarket sports discovery instead of only static priors.

## What the bundled live mode does

The bundled `scripts/market_bot.py` can now:
- fetch active Polymarket events from the public Gamma API
- sort by nearest end date
- inspect each event's markets
- auto-detect likely sport from series slug, ticker, event title, market slug, and market question
- save a local JSON snapshot for later filtering or analysis
- inspect a specific market or event URL/slug and report the detected sport plus current implied YES price
- produce an initial heuristic auto-forecast scaffold from a live market URL or slug
- rank multiple live markets from a snapshot and optionally auto-log the ranked results

## Main commands

### 1) Sync live sports snapshot

```bash
python scripts/market_bot.py sync-live-sports \
  --pages 3 \
  --per-page 100 \
  --include-unknown \
  --output data/polymarket-sports-live.json
```

Recommended defaults:
- `--pages 3` to `--pages 10` depending on how broad a scan you want
- `--per-page 100` for efficiency
- `--include-unknown` when you want sports-like markets that were not mapped confidently to a known sport family

### 2) Inspect a single live market

```bash
python scripts/market_bot.py inspect-live-market \
  "https://polymarket.com/event/cbb-xav-clmsn-2025-11-23"
```

You can also pass a slug directly:

```bash
python scripts/market_bot.py inspect-live-market cbb-xav-clmsn-2025-11-23
```

### 3) Auto-forecast from a live market URL or slug

```bash
python scripts/market_bot.py auto-forecast-live \
  "https://polymarket.com/event/cbb-xav-clmsn-2025-11-23"
```

Optional refinement inputs:

```bash
python scripts/market_bot.py auto-forecast-live \
  cbb-xav-clmsn-2025-11-23 \
  --injury-impact -0.03 \
  --form-impact 0.04 \
  --schedule-impact 0.02 \
  --anchor-to-market 0.2
```

The auto-forecast mode:
- fetches the live market
- detects the sport
- infers an initial prior profile from market implied probability
- infers whether YES is being treated as favorite or underdog
- optionally blends part of the estimate back toward market price
- outputs a forecast scaffold, not a final guaranteed prediction

### 4) Rank live markets and auto-log the results

```bash
python scripts/market_bot.py rank-live-markets \
  --snapshot data/polymarket-sports-live.json \
  --sport basketball \
  --limit 10 \
  --log-output data/ranked-auto-forecasts.jsonl
```

Use `--refresh` if you want to fetch a new snapshot first.

The ranking score is heuristic and blends:
- model-vs-market edge size
- liquidity
- volume

This is for triage and prioritization, not proof of alpha.

### 5) Run one full auto cycle

```bash
python scripts/market_bot.py auto-cycle \
  --sport basketball \
  --limit 20 \
  --summary-limit 5 \
  --summary-output data/auto-cycle-summary.json
```

What this does in one command:
- refreshes the live snapshot
- ranks markets
- appends ranked rows to the JSONL log
- writes a compact summary JSON
- renders a modern HTML dashboard snapshot

This is the mode to pair with cron if you want scheduled automation.

### 6) Find late-game high-confidence live locks

```bash
python scripts/market_bot.py find-live-locks \
  --refresh \
  --min-probability 0.90 \
  --limit 20 \
  --log-output data/live-locks.jsonl
```

This mode is designed for the exact idea of:
- in-play sports markets
- very little time left
- leader already clearly ahead
- heuristic win probability around 90%+

Example logic:
- soccer at ~85' with a 2-goal lead
- basketball late in Q4 with a multi-possession lead
- hockey late in the 3rd with a 2-goal lead

### 7) Run a dedicated live-lock automation cycle

```bash
python scripts/market_bot.py auto-live-locks \
  --refresh \
  --min-probability 0.90 \
  --limit 20 \
  --summary-limit 10
```

This mode is the specialized scanner for:
- all sports
- late-game only
- strongest high-probability closeout states
- one main summary/log/dashboard workflow

Recommended main outputs:
- `data/summary.json`
- `data/dashboard.html`
- `data/live-locks.jsonl`

### 8) Build the dashboard manually

```bash
python scripts/build_dashboard.py \
  --summary data/auto-summary.json \
  --log data/auto-log.jsonl \
  --snapshot data/auto-snapshot.json \
  --output data/dashboard.html
```

Open `data/dashboard.html` in your browser.

## Output snapshot shape

The snapshot JSON contains:
- `generated_at`
- `source`
- `ordering`
- `counts_by_sport`
- `total_items`
- `items[]`

Each item includes fields such as:
- event title / slug
- market question / slug
- detected sport
- detection confidence
- detection hits
- series slug / ticker / title
- volume and liquidity
- implied YES probability when available
- best bid / ask
- sports market type
- line
- event URL

## Detection logic

Sport detection uses:
- exact and fuzzy matching against bundled sport aliases
- series data like `nba`, `ncaa-cbb`, `f1`, `ufc`, `atp`, `wta`, `ipl`, `nhl`, `mlb`
- event and market wording
- sports-specific metadata such as `sportsMarketType`, `gameId`, `teamAID`, `teamBID`, or `gameStatus`

This means detection is useful, but not perfect.

## Limitations

- It is a lightweight public-data sync, not an official full mirroring pipeline.
- Polymarket listings change constantly; a snapshot is only current at fetch time.
- Some sports-like markets may map to `unknown-sport` if league or series naming falls outside the bundled alias set.
- The script discovers markets and implied prices; it does not automatically produce a final forecast without a human or higher-level reasoning step.

## Recommended workflow

1. Run `sync-live-sports`
2. Pick a market of interest from the snapshot
3. Run `inspect-live-market` on that slug or URL
4. Use either `sports` for manual structured analysis or `auto-forecast-live` for a faster heuristic scaffold
5. Log the final view with `scripts/forecast_log.py`

## Example end-to-end

```bash
python scripts/market_bot.py sync-live-sports --pages 3 --per-page 100 --output data/polymarket-sports-live.json
python scripts/market_bot.py inspect-live-market cbb-xav-clmsn-2025-11-23
python scripts/market_bot.py auto-forecast-live cbb-xav-clmsn-2025-11-23 --form-impact 0.03 --anchor-to-market 0.2
python scripts/forecast_log.py --log data/forecast-log.jsonl add cbb-xav-clmsn-2025-11-23 "Xavier Musketeers vs. Clemson Tigers" 0.53 --market-implied-probability 0.50 --confidence medium --rationale "Heuristic prior plus matchup adjustments"
```
