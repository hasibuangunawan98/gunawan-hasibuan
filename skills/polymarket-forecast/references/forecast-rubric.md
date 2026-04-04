# Forecast Rubric

Use this reference when you need a more disciplined prediction-market workflow.

## 1. Resolution check

Before any estimate, verify:
- exact market wording
- resolution source
- resolution deadline
- ambiguity risk
- possibility of market invalidation or disputed interpretation

If ambiguity risk is high, cap confidence at **low** unless the wording is clarified.

## 2. Evidence scoring

Score each key piece of evidence from 1 to 5.

### Source quality
- 5 = official filing, official release, court order, regulator notice, direct data source
- 4 = reputable reporting with strong sourcing
- 3 = credible analyst synthesis or indirect but plausible reporting
- 2 = social/media commentary without independent confirmation
- 1 = rumor or anonymous speculation

### Relevance
- 5 = directly changes market resolution odds
- 4 = strong indirect signal
- 3 = useful context only
- 2 = weakly related
- 1 = mostly noise

### Freshness
- 5 = same day / immediately current
- 4 = recent and still actionable
- 3 = somewhat stale but relevant
- 2 = old context
- 1 = outdated for this market

Use high-confidence evidence when at least one important item scores strongly across all three dimensions.

## 3. Confidence checklist

Set confidence using this rubric:

### High
Use only when most are true:
- resolution criteria are clear
- evidence is current and mostly primary
- base rate is known or easy to estimate
- few hidden variables remain
- forecast would not change much with one extra headline

### Medium
Use when:
- wording is mostly clear
- evidence is decent but incomplete
- there are a few meaningful unknowns
- estimate is directionally solid but not robust to major news

### Low
Use when any of these are true:
- market wording is ambiguous
- resolution source is unclear
- evidence is thin, stale, or contradictory
- the question depends on insider or hard-to-observe information
- timing dominates more than fundamentals

## 4. Probability discipline

When choosing a point estimate:
- start with a range
- ask what evidence would move you by 10 points or more
- avoid crossing key thresholds (50, 60, 70, 80) without explicit reasons
- avoid extreme estimates above 90 or below 10 unless the resolution path is unusually clear

## 5. Mispricing check

A market can look wrong for bad reasons. Before calling it a mispricing, check:
- low liquidity
- wide spreads
- stale market reaction
- ambiguous resolution terms
- hidden information the market may already know
- event timing mismatch

## 6. Suggested analysis template

```markdown
### Market
- Restated market: ...
- Resolution source/deadline: ...

### Estimate
- YES probability: ...
- Confidence: low / medium / high

### Evidence
- Strongest evidence for YES: ...
- Strongest evidence for NO: ...
- Evidence quality notes: ...

### Pricing check
- Market implied probability: ...
- Difference vs estimate: ...
- View: ...

### Risks
- ...
- ...

### Update triggers
- If X happens, move estimate to ...
- If Y happens, move estimate to ...
```

## 7. Backtesting log fields

For repeated forecasting, store at least:
- date/time forecast made
- market URL or unique ID
- market text
- resolution date
- estimated YES probability
- market implied probability at forecast time
- confidence level
- short rationale
- outcome after resolution

Optional metrics:
- Brier score
- calibration by bucket (0-10%, 10-20%, etc.)
- average edge vs close price
- hit rate by confidence level

## 8. Guardrails

Do not:
- promise profit
- promise fixed win rate
- present uncertain claims as facts
- ignore contradictory evidence
- confuse market price with truth

Prefer honest uncertainty over confident nonsense.