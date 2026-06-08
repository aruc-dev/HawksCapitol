# Backtesting

Backtests replay disclosures by `filing_date`. A simulated day can only see filings
whose `filing_date` is on or before that day; `tx_date` is used only for lag, decay,
and closed-window return calculations.

The default validation gate reports `pass`, `watch`, or `fail`. Live promotion cannot
use an in-sample result alone: the report includes a walk-forward split note, and paper
results must validate out of sample before any live-mode discussion.
