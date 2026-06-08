# Backtesting

Backtests replay disclosures by `filing_date`. A simulated day can only see filings
whose `filing_date` is on or before that day; `tx_date` is used only for lag, decay,
and closed-window return calculations.

## Checked-In Dataset

Non-dry-run backtests default to the checked-in official House Clerk dataset at
`data/backtest/official_house_6mo/transactions.json`. The manifest is stored next to
it at `data/backtest/official_house_6mo/manifest.json`.

Current dataset:

- source: official House Clerk PTR ZIP/XML indexes and PTR PDFs;
- filing window: 2025-12-01 through 2026-06-04;
- pulled on: 2026-06-08;
- filings: 278;
- canonical transactions: 2,188;
- buy transactions: 1,173;
- Senate eFD is not included in this checked-in fixture.

Run the real-data backtest:

```bash
python3 scheduler/run_backtest.py --days 186
```

Run the deterministic sample backtest used by CI:

```bash
python3 scheduler/run_backtest.py --dry-run
```

Use a different checked-in dataset without writing a report:

```bash
python3 scheduler/run_backtest.py --dry-run --dataset path/to/transactions.json
```

## Market Data Limitation

The checked-in dataset contains official disclosure transactions only. It does not
include approved historical market-price data. Until a reviewed free market-data source
or Alpaca paper market-data export is added, reports with
`market_data.price_history_supplied=false` use the simulator fallback return model.
Those results are useful for replay/gating validation, but they are not price-realized
performance.

The default validation gate reports `pass`, `watch`, or `fail`. Live promotion cannot
use an in-sample result alone: the report includes a walk-forward split note, and paper
results must validate out of sample before any live-mode discussion.
