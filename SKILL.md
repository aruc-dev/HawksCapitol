# HawksCapitol Implementation Skill

Use this skill when building, reviewing, or deploying HawksCapitol.

## Workflow

1. Read `architecture.md` for system behavior and invariants.
2. Read `plan.md` for the current build phase and acceptance criteria.
3. Run `bd ready` from `HawksCapitol/`, then claim or create a local issue.
4. Make the smallest scoped implementation change that satisfies the issue.
5. Add or update unit tests and validation tests in the same change.
6. Run the full local validation required by `AGENTS.md`.
7. Close the Beads issue only after validation is complete.

## Non-Negotiable Invariants

- Point-in-time correctness: trading decisions use `filing_date` visibility, never
  future transaction knowledge.
- Free-source compliance: official filings are source of truth; optional APIs must pass
  source-registry validation before production use.
- Paper-first execution: live mode is blocked unless explicitly approved in-session.
- Independent exits: do not wait for late congressional sell filings to manage risk.
- Risk integrity: sizing, stops, profit targets, and live promotion gates require human
  approval before material changes.

## Test Expectations

Every meaningful change must include tests that would fail without the change.

Required test classes by area:

- `tests/test_sources_*.py` for source adapters, fixtures, source health, and eligibility.
- `tests/test_ingestion_*.py` for parsing, normalization, dedupe, amendments, and idempotency.
- `tests/test_analytics_*.py` for point-in-time scoring, sample-size guards, and alpha decay.
- `tests/test_engine_*.py` for signal gates, sizing, risk caps, blocked reasons, and exits.
- `tests/test_execution_*.py` for Alpaca paper behavior, live guard, idempotent orders, and reconciliation.
- `tests/test_backtest_*.py` for no-lookahead replay, reproducibility, and validation gates.

Validation commands must be recorded in the Beads close reason or notes.
