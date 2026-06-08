# HawksCapitol Agent Instructions

HawksCapitol is a paper-first congressional trade copy-trading system. Its AWS
provisioning is Terraform-first, runnable from a laptop now and GitHub Actions later.
The runtime still uses the Hawks family pattern: Python, Alpaca, AWS EC2, systemd
timers, AWS Secrets Manager, and tmpfs secrets.

## Required Startup Checks

- Confirm you are working in the `HawksCapitol/` repository.
- Run `bd ready` from this directory before starting work.
- Claim or create a Beads issue before modifying files.
- Read `architecture.md`, `plan.md`, and `SKILL.md` for the current design and workflow.
- Confirm `mode: paper` remains the default. Do not switch to live without explicit
  human approval in the current session.
- Include a documentation check in the issue scope before editing: identify whether
  `AGENTS.md`, `SKILL.md`, `README.md`, `TESTING.md`, `architecture.md`, `plan.md`, or
  `docs/` need updates for the change.

## Absolute Rules

1. Never commit secrets, `.env` files, API keys, or `*.pem` files.
2. Never use paid, private, trial-only, or terms-unreviewed data sources.
3. Never bypass official-site access controls or scrape a third-party site unless its
   terms explicitly allow automated access.
4. Never place live trades unless the user explicitly transitions the session to live.
5. Never change risk parameters without explicit human approval.
6. Never deploy non-main branches or extra commits to a live remote system without
   explicit human approval.

## Testing Required For Every Change

Every code change must include or update focused unit tests and run the relevant
validation command before the Beads issue is closed.

Minimum local validation:

```bash
python3 -m unittest discover -v
python3 scheduler/<affected_runner>.py --dry-run
git diff --check
```

Additional validation is required by touched area:

- Ingestion/source changes: fixture/golden-file parser tests, no live network in CI,
  idempotency tests, source-registry validation.
- Analytics/scoring changes: point-in-time lookahead tests and deterministic fixture
  outputs.
- Signal/risk changes: cap, sizing, blocked-reason, and stale-data tests.
- Execution changes: paper-only tests, idempotent client order IDs, live-mode guard,
  order-governor tests.
- Backtest changes: no-lookahead tests, reproducibility checks, benchmark comparisons.
- Remote changes: verify services, timers, dry-runs/health checks, logs, and monitor
  for at least 10 minutes before closing.
- Terraform/deploy changes: run or explicitly account for `scripts/validate_terraform.sh`,
  verify no secret values are stored in Terraform state/examples, and document any
  required AWS/GitHub Actions variables.

## Documentation Check Required For Every Change

Every change, including code, tests, deployment artifacts, configuration, and process
updates, must include a documentation check before the Beads issue is closed.

For each issue:

- Update the affected documentation in the same change, or record a clear
  no-documentation-needed rationale in the Beads close reason.
- Keep agent/process docs current when workflow expectations change.
- Keep `README.md`, `TESTING.md`, `architecture.md`, `plan.md`, and `docs/` aligned
  with implemented behavior, scheduler commands, deployment requirements, and safety
  gates.
- Include documentation validation in the close reason, usually `git diff --check` plus
  the focused docs contract tests when documentation rules or public commands change.

## Beads Workflow

Use the local HawksCapitol tracker:

```bash
bd ready
bd create "short task title" --type task
bd update <id> --claim
bd close <id> --reason "validated with ..."
```

Do not use the parent HawksTradeOperations tracker for code or docs changed inside
`HawksCapitol/`, except for operations-only EC2 interventions that do not change this
repository.

## Remote Repository

The remote `origin` is:

```bash
https://github.com/aruc-dev/HawksCapitol.git
```

Verify with `git remote -v` before pushing or deploying. Live deployments remain
restricted to approved `origin/main`.
