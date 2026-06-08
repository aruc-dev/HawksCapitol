# Scoring

HawksCapitol scoring is point-in-time:

- disclosures become visible on `filing_date`;
- `tx_date` is used only for lag/decay math;
- future disclosures and future committee assignments are never visible in past
  simulations;
- sparse sample sizes reduce or block member scores;
- entry quality penalizes stale filings, large filing gaps, event risk, and low parse
  confidence.
