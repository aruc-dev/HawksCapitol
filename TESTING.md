# Testing HawksCapitol

Run the full local test suite:

```bash
python3 -m unittest discover -v
```

Run scheduler dry-runs:

```bash
python3 scheduler/run_ingest.py --dry-run
python3 scheduler/run_score.py --dry-run
python3 scheduler/run_scan.py --dry-run
python3 scheduler/run_risk_check.py --dry-run
python3 scheduler/run_backtest.py --dry-run
python3 scheduler/run_report.py --dry-run
python3 scheduler/run_health_check.py --dry-run
```

Every code change should include a focused test that fails without the change.
Network-backed source adapters must be tested with fixtures or recorded payloads, not
live network calls in CI.
