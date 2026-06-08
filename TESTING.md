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
python3 scheduler/run_weekly_report.py --dry-run
python3 scheduler/run_health_check.py --dry-run
python3 scheduler/run_live_promotion_check.py --dry-run
```

Run the checked-in real-data backtest and write `reports/backtest/latest.json`:

```bash
python3 scheduler/run_backtest.py --days 186
```

The checked-in real-data backtest currently uses official House disclosure data plus
the simulator fallback return model unless a report shows
`market_data.price_history_supplied=true`.

Validate Terraform deployment artifacts:

```bash
scripts/validate_terraform.sh
```

Run the local paper deployment readiness gate before any paper EC2 deployment:

```bash
scripts/validate_paper_deploy.sh
```

Every code change should include a focused test that fails without the change.
Network-backed source adapters must be tested with fixtures or recorded payloads, not
live network calls in CI.

Every change must also include a documentation check. Update affected documentation in
the same change, or record a no-documentation-needed rationale in the Beads close
reason. Documentation/process changes should run the focused docs contract tests plus
`git diff --check`.
