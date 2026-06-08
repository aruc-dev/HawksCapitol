# HawksCapitol

![HawksCapitol Brand](assets/brand/hawkscapitol-brand.png)

Paper-first congressional trade copy-trading system using free public STOCK Act
disclosures, point-in-time scoring, Alpaca-compatible execution boundaries, and
lag-aware exit/risk controls.

## Current State

This repository contains a locally validated, production-paper-ready implementation:

- file-backed config, canonical data, reports, and paper broker state;
- official House Clerk and Senate eFD ingestion helpers with fixture-friendly adapters;
- source registry enforcement for free/authorized data feeds;
- optional source adapters that self-disable unless source-policy gates pass;
- point-in-time member scoring, alpha decay, and sector heatmaps;
- copy-buy signal generation with entry-quality, liquidity, event, and risk gates;
- independent sell engine for stale filing risk, profit targets, stops, and alpha decay;
- persistent Alpaca-compatible paper execution, reconciliation, reports, and backtesting;
- daily/weekly reports, health checks, and a read-only dashboard renderer;
- AWS Secrets Manager to tmpfs materialization and `hawkscapitol-*` systemd timers;
- Terraform-based AWS provisioning for laptop deployment now and GitHub Actions
  deployment later;
- local paper deployment readiness validation with live promotion blocked by default;
- unit tests for source, PIT, signal, risk, execution, deploy, reporting, and docs
  invariants.

The remaining external paper-production step is a reviewed Terraform apply, paper secret
value creation, and 10-minute systemd monitor on HCEC2P.

## Quick Start

```bash
python3 -m unittest discover -v
python3 scheduler/run_ingest.py --dry-run
python3 scheduler/run_score.py --dry-run
python3 scheduler/run_scan.py --dry-run
python3 scheduler/run_risk_check.py --dry-run
python3 scheduler/run_backtest.py --dry-run
python3 scheduler/run_report.py --dry-run
python3 scheduler/run_weekly_report.py --dry-run
python3 scheduler/run_health_check.py --dry-run
python3 scheduler/run_live_promotion_check.py --dry-run
scripts/validate_terraform.sh
scripts/validate_paper_deploy.sh
```

The default config is `mode: paper`. Live execution is blocked unless explicitly
approved in-session and configured in `config/config.yaml`.

## Runtime Data Safety

`scheduler/run_scan.py --dry-run` uses fixture transactions for local validation.
Without `--dry-run`, the scan reads canonical transactions from
`<data_dir>/canonical/transactions.json` and the sector map from `config/sectors.json`;
missing canonical transactions produce no signals or paper orders rather than falling
back to demo data.
Non-dry-run daily and weekly reports aggregate persisted runtime artifacts, such as
latest signals, backtest output, risk decisions, and health status, instead of invoking
dry-run fixture paths.

## AWS Deployment

HawksCapitol is Terraform-first for AWS deployment:

```bash
cd infra/terraform
cp terraform.tfvars.example terraform.tfvars
terraform init
terraform plan
terraform apply
```

The Terraform module provisions the paper EC2 node, IAM role/profile, Secrets Manager
metadata, networking, and systemd bootstrap. It does not store secret values in
Terraform state. Add the `hawkscapitol/keys` secret value through AWS Secrets Manager,
then set `enable_systemd_timers = true` and apply again.

See `infra/terraform/README.md` and `cloud-setup/aws-setup-systemd.md`.

## Documentation Discipline

Every change must include a documentation check. Update affected docs in the same change
or record a no-documentation-needed rationale in the Beads close reason. See
`AGENTS.md`, `SKILL.md`, and `TESTING.md` for the required workflow.
