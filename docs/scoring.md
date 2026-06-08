# Scoring

HawksCapitol scoring is point-in-time:

- disclosures become visible on `filing_date`;
- `tx_date` is used only for lag/decay math;
- future disclosures and future committee assignments are never visible in past
  simulations;
- sparse sample sizes reduce or block member scores;
- entry quality penalizes stale filings, large filing gaps, event risk, and low parse
  confidence.

Alpha-decay curves are computed only from closed historical buy episodes. A trade is
eligible for a horizon only when its `filing_date` is visible as of the score date and
the full forward window has completed by that same as-of date. `freshness_score` then
discounts copy entries from `tx_date`, with optional curve-derived max positive age.

Member scores combine sample quality, PIT hit rate, closed-window realized alpha,
filing latency, disclosed amount tier, parse quality, and sector concentration. When
price history is unavailable, alpha and hit-rate components remain neutral instead of
using future data. Members below the configured minimum sample size are capped below
the entry threshold.

Sector heatmaps include only filings visible as of the report date and, by default,
only recent filed buys. Profitability fields use the same closed-window rule as member
scoring.
