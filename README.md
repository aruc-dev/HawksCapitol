# HawksCapitol

![HawksCapitol Brand](assets/brand/hawkscapitol-brand.png)

Paper-first congressional trade copy-trading system using free public STOCK Act
disclosures, point-in-time scoring, Alpaca-compatible execution boundaries, and
lag-aware exit/risk controls.

## Current State

This repository contains a runnable MVP scaffold:

- file-backed config, canonical data, reports, and paper broker state;
- official-source ingestion helpers and fixture-friendly source adapters;
- source registry enforcement for free/authorized data feeds;
- point-in-time member scoring and alpha decay;
- copy-buy signal generation with entry-quality and risk gates;
- independent sell engine for stale filing risk;
- paper execution, reconciliation, reports, and backtesting;
- scheduler entrypoints with `--dry-run`;
- unit tests for the core invariants.

## Quick Start

```bash
python3 -m unittest discover -v
python3 scheduler/run_ingest.py --dry-run
python3 scheduler/run_score.py --dry-run
python3 scheduler/run_scan.py --dry-run
python3 scheduler/run_risk_check.py --dry-run
python3 scheduler/run_backtest.py --dry-run
python3 scheduler/run_report.py --dry-run
python3 scheduler/run_health_check.py --dry-run
```

The default config is `mode: paper`. Live execution is blocked unless explicitly
approved in-session and configured in `config/config.yaml`.
