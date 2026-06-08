# HawksCapitol — Development Plan

**Companion to:** [`architecture.md`](./architecture.md)
**Audience:** AI coding agents (Claude / Codex / Gemini) and human reviewers
**Goal:** Take HawksCapitol from empty repo → validated, paper-trading deployment that
copies U.S. congressional trades from free sources with an intelligent, lag-aware
sell engine.

> **How to use this plan.** Build phases **in order**. Each phase lists deliverables,
> concrete tasks, and **acceptance criteria** that must be green before moving on. File
> one Beads issue per task (`bd create`), follow the mandatory workflow in `AGENTS.md`,
> add/update tests for every change, and never mark a phase done until its tests pass
> and (for any remote change) the instance is validated. **Paper mode only** until
> §Phase 9 explicitly promotes to live with human approval.

---

## 0. Conventions & Definition of Done

- **Language/stack:** Python 3.10+, file-based persistence (CSV/JSON), Alpaca broker,
  Terraform-provisioned AWS, and systemd on Amazon Linux 2023. Reuse HawksTrade modules
  wherever possible (port, don't reinvent: `alpaca_client`, `order_executor`,
  `order_governor`, `risk_manager`,
  `correlation_guard`, `atr_sizing`, `exit_policy`, `live_mode_guard`, `config_loader`,
  `logging_config`).
- **Every task is Done only when:** the change includes focused unit tests or an explicit
  no-code-test rationale, documentation has been checked and updated or explicitly
  marked not needed, validation tests pass, the relevant `scheduler/*.py --dry-run`
  runs clean, no secrets are logged, and the Beads issue is closed and pushed.
- **Every change must be validated:** each Beads issue close reason must list the unit
  tests, documentation check, and validation commands run. Remote paper/live changes
  require full service, timer, dry-run/health, log, and monitoring validation before
  close.
- **Point-in-time rule (non-negotiable):** anything that decides *what was knowable when*
  must key off `filing_date`, never `tx_date`. A PR that violates this is rejected.
- **Free sources only.** No paid feeds. No non-public data.
- **Source eligibility gate:** every automated source must be registered with cost,
  terms, rate limit, and production status. Config validation blocks paid, unknown,
  trial-only, private, or terms-unreviewed sources.
- **Safety:** no live orders, no `mode: live`, no risk-parameter changes without explicit
  human approval in-session.

---

## 0.1 Required Test & Validation Matrix

Every implementation task must add or update tests in the same change. The only
exception is a docs-only change, which must still run markdown/whitespace checks.
Every implementation task must also perform a documentation check and update affected
docs in the same change when behavior, commands, configuration, deployment, or workflow
expectations change.

| Change Area | Required Unit Tests | Required Validation |
|---|---|---|
| Source adapters | fixture fetch/parse tests, source health, source-registry eligibility | no live network in CI; `run_ingest.py --dry-run`; idempotency check |
| PDF/OCR/normalization | golden-file parser tests, low-confidence handling, amendment handling | fixture ingest produces stable canonical JSON |
| Ticker/member/committee data | resolver tests, alias tests, PIT committee snapshot tests | unresolved rows flagged; no future committee data in backtests |
| Analytics/scoring | PIT lookahead tests, sparse-sample guard, deterministic formula output | `run_score.py --dry-run`; score docs updated |
| Signal generation | freshness, entry-quality, blocked-reason, sizing, exposure cap tests | synthetic scan dry-run with no orders |
| Sell/risk engine | each exit rule, priority order, stale-price behavior, alpha-decay stop | `run_risk_check.py --dry-run`; protective-exit log review |
| Execution/broker | live-mode guard, order governor, idempotent client order IDs, reconciliation | Alpaca paper validation only; no live orders |
| Backtesting | no-lookahead replay, reproducibility, benchmark comparisons | `run_backtest.py --days N`; report saved |
| Reporting/dashboard | report fixture tests, source freshness alerts, read-only dashboard tests | local dashboard smoke test / screenshot where applicable |
| Terraform/deploy | Terraform artifact tests, unit rendering tests, env-path tests, timer naming tests | `scripts/validate_terraform.sh`; `daemon-reload`, service/timer status, logs, health, 10-minute monitor on remote |
| Documentation/process | docs contract tests when workflow/public commands change | documentation check recorded; `git diff --check` |

Baseline commands:

```bash
python3 -m unittest discover -v
python3 scheduler/<affected_runner>.py --dry-run
git diff --check
```

---

## Phase 0 — Project Scaffolding & Agent Manuals
**Objective:** a runnable skeleton that mirrors the Hawks family conventions.

Tasks
1. Create repo structure from `architecture.md` §7.2; init git; add `.gitignore`
   (exclude `.env`, `data/raw/`, `logs/`, `*.pem`, `__pycache__`).
2. Author required agent files: root `AGENTS.md` and root `SKILL.md`. `AGENTS.md` must
   define Beads workflow, paper/live guardrails, free-source rules, risk approval rules,
   and mandatory per-change tests. `SKILL.md` must summarize the implementation workflow,
   invariants, and test expectations for AI agents.
3. Author optional agent mirrors: `CLAUDE.md`, `CODEX.md`, `GEMINI.md` — port the
   HawksTrade structure (mandatory Beads workflow, identity checks, guardrails, deploy
   table incl. **HCEC2P/HCEC2L**, verification requirements).
4. `requirements.txt` (alpaca-py, pandas, numpy, pyyaml, python-dotenv, requests,
   beautifulsoup4/lxml, pdfplumber/pypdf, pytesseract+pillow for OCR, rapidfuzz,
   tabulate, pyarrow, yfinance), `pyproject.toml`, `TESTING.md`, `README.md`.
5. `config/config.yaml` skeleton (`mode: paper`, `secrets_source`, source toggles, all
   thresholds with safe defaults), `config/source_registry.yaml`, `config/.env.example`,
   `config/sectors.json` (reuse), `config/members.json` seed.
6. `core/config_loader.py`, `core/logging_config.py`, `core/version.py` (ported).
7. `docs/sources.md` and `docs/scoring.md` stubs; source docs are generated or updated
   from `source_registry.yaml` whenever adapters change.
8. Initialize a dedicated **Beads tracker** for the repo with `bd init --prefix HawksCapitol`.
9. Configure git `origin` as `https://github.com/aruc-dev/HawksCapitol.git`; verify with
   `git remote -v`. Do not push until the scaffold is reviewed and ready.

Acceptance
- `python3 -c "import sys; sys.path.insert(0,'.'); import core.config_loader"` works.
- `python3 -m unittest discover -v` runs (zero or passing tests).
- `config_loader` loads `config.yaml` and validates required keys; missing keys fail loud.
- Config validation rejects any enabled source that is paid, unknown, trial-only, or
  missing `terms_reviewed_at` / `automated_access_allowed`.
- `bd where` from `HawksCapitol/` reports prefix `HawksCapitol`.
- `AGENTS.md` and `SKILL.md` exist and describe per-change testing/validation.

---

## Phase 1 — Ingestion: Official Sources (source of truth)
**Objective:** reliably fetch and parse House + Senate PTRs into canonical records.

Tasks
1. `sources/base.py` — `DisclosureSource` protocol + `RawFiling`, `SourceHealth`.
2. `sources/house_clerk.py` — download `<YEAR>FD.zip`, parse `<YEAR>FD.xml`, filter
   `FilingType=P`, fetch PTR PDFs by `DocID`. Cache + conditional GET + backoff.
3. `ingestion/pdf_parser.py` + `ingestion/ocr.py` — text-PDF extraction with OCR
   fallback; emit `parse_confidence`.
4. `sources/senate_efd.py` — agreement-cookie + CSRF flow → POST search → fetch
   electronic (HTML) and paper (PDF→OCR) PTRs. Polite rate limiting.
5. `ingestion/normalizer.py` — map raw rows → canonical `Member`/`Disclosure`/
   `Transaction` (§4); classify `asset_type`; parse amount ranges → min/max/mid; parse
   option metadata when present; compute `filing_lag_days` and `filing_gap_pct` when
   prices are available.
6. `sources/committee_memberships.py` — ingest official House/Senate/Congress.gov
   committee data into PIT snapshots for sector-relevance scoring.
7. `sources/ticker_resolver.py` — issuer-name → symbol (fuzzy + cached table; handle
   renames/delistings).

Acceptance
- Given fixture ZIP/XML/PDF + recorded eFD responses, parsers produce expected
  canonical records (golden-file tests; **no live network in CI**).
- `scheduler/run_ingest.py --dry-run --source house_clerk` ingests a sample window and
  writes canonical JSON to `data/canonical/` idempotently (re-run = no duplicates).
- ≥95% ticker-resolution on a labeled fixture set; unresolved rows flagged, not dropped.
- Committee snapshots are dated and PIT-safe; a backtest cannot use future committee
  assignments.

---

## Phase 2 — Ingestion: Optional Free APIs + Reconciliation
**Objective:** faster notice + cross-validation; single deduplicated truth.

Tasks
1. `sources/fmp.py` — optional free-key adapter. It must self-disable when quota,
   entitlement, or endpoint access is unavailable; no paid plan is assumed.
2. `sources/congressinvests.py` — optional free-key adapter if current request limits
   and terms allow automated use.
3. `sources/capitoltrades_reference.py` — manual-reference metadata only; no automated
   scraping unless a durable free API and acceptable terms are verified.
4. `sources/finnhub.py` — disabled stub only unless future source-registry review proves
   congressional trading access is free/non-paid; current assumption is premium.
5. `ingestion/dedupe.py` — dedup by `(member, asset, tx_type, tx_date, amount_range)`
   with fuzzy matching; collapse amendment lineage (`amends_doc_id`).
6. `ingestion/reconciler.py` — official record wins on conflict; log discrepancies with
   confidence; emit a reconciliation report.
7. `sources/stock_watcher.py` — bulk historical loader for backtests (history only and
   only if license/reuse terms pass source-registry review).
8. `scheduler/run_ingest.py` — orchestrate all enabled sources; per-source health.

Acceptance
- Mixed-source fixtures collapse to the correct deduplicated set; official beats API on
  conflict; amendments supersede.
- Disabling any one source still yields a valid run (resilience test).
- Per-source `health()` reported; stale/failed sources flagged.
- Paid/unknown/manual-reference sources cannot be enabled in production config.

---

## Phase 3 — Analytics: Scoring & Alpha Decay (point-in-time)
**Objective:** know *who* and *which sectors* are worth copying, and *how fresh* a signal is.

Tasks
1. `analytics/alpha_decay.py` — forward-return curves of disclosed buys vs SPY over
   30/90/180d on **closed historical** episodes; produce `freshness_score(tx_date)`.
2. `analytics/member_score.py` — PIT hit-rate, realized alpha, filing latency, activity,
   concentration, sample size, confidence bands → normalized `score`. **Must not** use
   future data.
3. `analytics/sector_heatmap.py` — recent copyable buy flow × historical profitability by
   sector; surface "hot/active" members & sectors.
4. `scheduler/run_score.py` — nightly recompute → `data/canonical/member_scores/`.

Acceptance
- PIT unit test: scores as-of date D use only disclosures with `filing_date ≤ D`
  (lookahead test fails the build if violated).
- Deterministic outputs on fixed fixtures; documented score formula in `docs/`.
- Sparse-member guard: members below minimum sample size cannot trigger entries alone.

---

## Phase 4 — Copy-Buy Signal Engine
**Objective:** turn fresh, high-conviction disclosed buys into sized candidates.

Tasks
1. `engine/conviction.py` — combine member score, cluster-buy stacking, amount tier,
   committee-sector relevance → `conviction_score`.
2. `engine/copy_signal.py` — candidate gate: asset-type allowed, ticker resolved &
   liquid (ADV/spread filter), `freshness ≥ thresh`, `conviction ≥ thresh`,
   `entry_quality ≥ thresh`, caps allow.
3. `engine/entry_quality.py` — filing lag, price move from transaction date to filing
   date, post-filing gap, earnings/corporate-action blackout, parse/source confidence,
   and regime gate.
4. Sizing: ATR risk %, scaled by `conviction × freshness × entry_quality`; enforce `max_position_pct`,
   `max_positions`, per-member cap, per-sector cap, correlation guard. (Reuse HawksTrade
   `atr_sizing`, `risk_manager`, `correlation_guard`.)
5. Emit `Signal` records with full provenance (`source_tx_ids`) + human rationale and
   `blocked_reason` for every skipped candidate.

Acceptance
- Fixture disclosures → expected ranked, sized `copy_buy` signals.
- All risk caps enforced (unit tests for each cap, incl. correlation rejection).
- Ranges never mirrored as dollar sizing (explicit test).
- Stale, low-confidence, large filing-gap, imminent-earnings, and source-unverified
  candidates are blocked with clear `blocked_reason`.

---

## Phase 5 — Intelligent Sell Engine
**Objective:** own exits independently of late member sell filings (architecture §5).

Tasks
1. `core/exit_policy.py` (port) + `engine/sell_engine.py` — ordered `ExitRule` set:
   hard stop-loss (ATR variant), profit target (+ optional scale-out), trailing/high-
   water, **alpha-decay time stop** (on `tx_date` effective age), event-driven (member
   sell filed / regime flip / earnings blackout), conviction-decay rebalance, max-hold cap.
2. Options exits: time-to-expiry stop + delta/IV-aware target (long options only).
3. Fail-safe protection: sync broker-side protective stops where supported; if local
   market data is stale, block entries, evaluate conservative exits from last-known
   prices only, and raise a health alert.
4. Wire into `scheduler/run_risk_check.py` (every ~15 min, market hours).

Acceptance
- Each exit rule has a unit test proving it triggers on the right condition and respects
  priority order (first match wins).
- Alpha-decay stop exits a position once effective age ≥ `max_alpha_age_days`.
- `run_risk_check.py --dry-run` evaluates a synthetic portfolio and logs decisions
  without placing orders.
- Stale-price test proves entries are blocked and open-position alerts fire.

---

## Phase 6 — Execution Layer (Alpaca, paper-first)
**Objective:** place/maintain orders safely; broker truth reconciled with intent.

Tasks
1. Port `core/alpaca_client.py`, `broker_interface.py`, `order_executor.py`,
   `order_governor.py`, `broker_stops.py`, `live_mode_guard.py`.
2. Add options order support (long calls/puts) behind a capability flag.
3. `scheduler/run_scan.py` — entries from Phase 4 signals (paper); `scheduler/
   reconcile_trade_log.py` — align trade-log with broker positions; protective stops sync.
4. `live_mode_guard`: refuse live unless `mode: live` **and** explicit human approval.
5. Idempotency: broker client must use client order IDs so retries do not duplicate
   orders; order reconciliation is broker-truth first.

Acceptance
- Against Alpaca **paper**, a candidate becomes a paper order, appears in trade-log, and
  reconciles to a broker position.
- `order_governor` blocks rate/notional breaches (test).
- Attempting live without approval is hard-blocked (test).
- Re-running scan after a transient failure does not duplicate an order.

---

## Phase 7 — Backtesting & Validation (point-in-time)
**Objective:** measure whether the strategy has edge *before* risking anything.

Tasks
1. `backtest/pit_replay.py` — replay disclosures in `filing_date` order; expose only
   what was public as-of each simulated day.
2. `backtest/simulator.py` — apply signal + sell engines with slippage/fees (reuse
   HawksTrade slippage model); compound a paper portfolio.
3. `backtest/metrics.py` — CAGR, Sharpe, max drawdown, hit rate, vs-SPY alpha, exposure,
   per-member/per-sector attribution.
4. `scheduler/run_backtest.py --days N` + a validation gate (min sample size, min
   Sharpe, drawdown ceiling) → `reports/`.
5. Baselines: compare against SPY, equal-weight copy-all, and no-entry-after-gap filters
   so the strategy must beat simpler alternatives before paper/live promotion.

Acceptance
- Lookahead guard test: injecting a future disclosure does **not** change a past day's
  decisions.
- Backtest over ≥3 years of history produces a metrics report; results saved & reproducible.
- Validation gate yields a clear pass/watch/fail verdict.
- Walk-forward split is documented; live promotion cannot rely on an in-sample-only pass.

---

## Phase 8 — Reporting, Health & Dashboard
**Objective:** observability and a human-readable view; alerts when sources go stale.

Tasks
1. `scheduler/run_report.py` (daily/weekly): P&L, new signals, exits + reasons, member/
   sector performance, **source-health, source-eligibility & data-freshness** digest.
2. `scheduler/run_health_check.py`: source reachability/freshness, broker reachability,
   stale-data and parse-confidence alarms → `reports/alerts/`.
3. `dashboard/` read-only Flask UI + Cloudflare tunnel (reuse HawksTrade dashboard +
   `hawkscapitol-cloudflared` unit).

Acceptance
- Reports generate from fixture state; freshness alarm fires when newest filing exceeds
  a staleness threshold.
- Dashboard renders portfolio, signals, and source health locally.
- Dashboard shows enabled/disabled/manual-reference source status and blocked-candidate
  reasons.

---

## Phase 9 — Deployment & Live Promotion (mirrors HawksTrade ops)
**Objective:** production paper deployment; live only on explicit approval.

Tasks
1. `scripts/fetch_secrets.sh` — AWS Secrets Manager (`hawkscapitol/keys`) → tmpfs
   `/dev/shm/.hawkscapitol.env`; `HAWKSCAPITOL_REQUIRE_SHM=1` in prod.
2. `scheduler/systemd/` units + timers (`hawkscapitol-*` per architecture §8.3), with
   secrets-before-trading ordering; plus `cron/` and `launchd/` for dev parity.
3. `cloud-setup/aws-setup-systemd.md` — IAM least-privilege (read-only Secrets Manager
   scoped to `hawkscapitol/*`), EC2 role, install steps (port from HawksTrade).
4. Deploy to **HCEC2P** following the operations-root `deploy` workflow (inspect →
   `origin/main` only → align units → `daemon-reload` → enable timers → validate →
   monitor ≥10 min). No trades placed during validation.
5. **Live promotion (separate, gated):** only after backtest + ≥N weeks paper meet the
   validation gate **and** the human explicitly approves in-session → configure
   `hawkscapitol/keys` live keys, set `mode: live` on **HCEC2L**, deploy `origin/main`
   only.
6. Update operations-root agent docs with real HCEC2P/HCEC2L hostnames only after EC2
   instances exist; until then aliases remain pending.

Acceptance
- HCEC2P: `systemctl list-timers 'hawkscapitol-*'` shows expected timers; secrets
  service populates tmpfs; dry-runs/health green; no errors in `journalctl`; 10-min
  monitoring clean.
- Live remains blocked by `live_mode_guard` until the explicit human go.

---

## Phase 10 — Hardening & Iteration (ongoing)
- Expand sources/members coverage; tune `member_score` weights from realized results.
- Walk-forward re-validation on a schedule; auto-disable members/sectors whose live
  edge decays (conviction-decay feedback loop).
- Optional: deeper options strategies via HawksOptions integration; notification
  channels (email/Slack); broaden asset handling.

---

## Build Order Dependency Graph
```
Phase 0 ─► 1 ─► 2 ─► 3 ─► 4 ─┐
                         └────► 5 ─► 6 ─► 7 ─► 8 ─► 9 ─► 10
```
Phases 4 and 5 may proceed in parallel after Phase 3; both must complete before Phase 6.

## Suggested Initial Beads Backlog (one issue per line)
```
HC-0  Scaffold repo + agent manuals + config + Beads tracker
HC-1  House Clerk ingestion + PDF/OCR parsing + ticker resolver
HC-2  Senate eFD ingestion (cookie/CSRF) + normalizer
HC-3  Source registry + optional free API adapters + dedupe + reconciliation
HC-4  Historical bulk loader (stock-watcher + Clerk ZIP archive)
HC-5  Committee/member snapshots + alpha-decay + freshness scoring
HC-6  Member scoring (PIT/sample quality) + sector heatmap
HC-7  Conviction + entry-quality model + copy-buy signal engine + sizing/caps
HC-8  Intelligent sell engine (all exit rules) + risk-check runner
HC-9  Alpaca execution (paper) + order governor + reconciliation
HC-10 Options long-call/put execution + exits
HC-11 Point-in-time backtester + simulator + metrics + validation gate
HC-12 Reporting + health checks + read-only dashboard
HC-13 Secrets + systemd units/timers + AWS setup doc
HC-14 Deploy HCEC2P + validate + 10-min monitor
HC-15 (gated) Live promotion criteria + HCEC2L
```

## Acceptance for the Whole System (v1)
1. Ingests House + Senate PTRs from free sources, deduplicated and reconciled, idempotently.
2. Source registry blocks paid/unknown/unauthorized sources from production.
3. Produces PIT-correct member/sector scores and fresh, sized copy-buy signals.
4. Entry-quality gates prevent stale, low-confidence, already-priced, or event-risk entries.
5. Manages exits via the intelligent-sell engine **without** depending on member sell filings.
6. Executes on Alpaca **paper** with full risk caps, governor, and reconciliation.
7. Backtests with **no lookahead**, producing a reproducible metrics report + validation verdict.
8. Reports, health-checks, and a read-only dashboard run on EC2 via systemd timers.
9. Live is reachable only behind `live_mode_guard` + explicit human approval.
