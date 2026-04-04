# Automation Workflow

Use this reference when turning the skill into a lightweight prediction bot.

## Goal

Produce a repeatable forecast loop:
1. inspect market wording
2. gather fresh evidence
3. score the evidence
4. estimate probability
5. compare against market price
6. log the forecast
7. review performance after resolution

## Recommended bot loop

### Step 1: Input normalization

For each market, capture:
- market ID or URL
- market text
- category (politics, crypto, macro, sports, regulation, product launch, etc.)
- resolution date
- current implied probability

Reject or flag markets with:
- unclear wording
- obvious resolution ambiguity
- ultra-low information environments
- categories where timely data is unavailable

### Step 2: Evidence collection

Gather evidence from several buckets:
- official source / rules / filings
- direct statements from relevant actors
- reputable news reporting
- historical/base-rate references
- market microstructure notes (liquidity, spread, stale price)

Keep evidence short and sourceable.

## Step 3: Scoring

For each major piece of evidence, score:
- source quality
- relevance
- freshness

Use `forecast-rubric.md` for the scoring rubric.

## Step 4: Forecast generation

Produce:
- YES probability
- NO probability
- confidence level
- strongest case for YES
- strongest case for NO
- what would change the estimate

## Step 5: Logging

Use the bundled script to maintain a JSONL backtest log.

### Add a forecast

```bash
python scripts/forecast_log.py --log data/forecast-log.jsonl add \
  market-123 \
  "Will X happen before 2026-12-31?" \
  0.62 \
  --market-implied-probability 0.54 \
  --confidence medium \
  --resolution-date 2026-12-31 \
  --rationale "Base rate is favorable, but timing risk remains." \
  --tags politics election
```

### Resolve a forecast

```bash
python scripts/forecast_log.py --log data/forecast-log.jsonl resolve market-123 yes
```

### Show stats

```bash
python scripts/forecast_log.py --log data/forecast-log.jsonl stats
```

## Step 6: Review and iterate

Review not only win rate but calibration quality:
- are 60% forecasts resolving about 60% of the time?
- is high confidence genuinely better than medium confidence?
- are misses concentrated in one category?
- are ambiguous markets poisoning the log?

## Guardrails for automation

Do not automate unbounded claims like:
- guaranteed alpha
- fixed 90% accuracy
- sure win
- risk-free edge

Prefer:
- candidate mispricing
- moderate edge if assumptions hold
- low-confidence view due to ambiguity

## Good operating habits

- focus on a small number of markets first
- specialize by category if possible
- avoid reacting to every headline equally
- track when the market moved before your evidence arrived
- keep rationale short enough that future review is easy
