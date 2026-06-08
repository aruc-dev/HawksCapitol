# Backtesting

Backtests replay disclosures by `filing_date`. A simulated day can only see filings
whose `filing_date` is on or before that day; trade candidates and non-SPY baselines
are constrained to the requested `--days` window. `tx_date` is used only for lag,
decay, and closed-window return calculations.

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

Real-data backtests require an Alpaca market-data export at
`data/backtest/official_house_6mo/prices.json`. Refresh it with Alpaca paper
credentials set in the environment:

```bash
APCA_API_KEY_ID=... APCA_API_SECRET_KEY=... python3 scripts/fetch_backtest_prices.py
```

The export stores adjusted daily closes for stock buy tickers plus `SPY`; commit the
generated `prices.json` with the matching transaction dataset. Non-dry-run
`scheduler/run_backtest.py` fails closed when this file is missing or does not include
`SPY`, so `reports/backtest/latest.json` is not produced from simulator fallback
returns. Dry-run sample runs still report `market_data.price_history_supplied=false`
and use the deterministic fallback model for CI fixture validation only.

The default validation gate reports `pass`, `watch`, or `fail`. Live promotion cannot
use an in-sample result alone: the report includes a walk-forward split note, and paper
results must validate out of sample before any live-mode discussion.
