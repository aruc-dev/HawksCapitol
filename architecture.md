# HawksCapitol — System Architecture

**Project:** HawksCapitol — Congressional Trade Copy-Trading System
**Status:** Design (pre-implementation)
**Owner:** Arun
**Last updated:** 2026-06-07
**Sibling systems:** HawksTrade (equities/crypto swing bot), HawksOptions (options bot)

> HawksCapitol is the third member of the Hawks family. It periodically ingests U.S.
> Congress (Senate + House) stock-trade disclosures from **free, public** sources,
> scores members and sectors by their historical edge, and **copies high-conviction
> trades** into an Alpaca brokerage account — **paper-first**. Because disclosures are
> filed *weeks after* the actual trade, the system never waits for a member's *sell*
> filing; instead it manages exits with its own **filing-lag-aware intelligent sell
> engine** (profit targets, trailing stops, alpha-decay timers, and signal-based
> exits).

This document is written to be **self-sufficient for an AI agent to implement the
entire system** from scratch. It pairs with [`plan.md`](./plan.md), which sequences
the build into phases with acceptance criteria.

---

## 1. Goals, Non-Goals, and Guardrails

### 1.1 Goals
1. **Ingest** congressional trade disclosures (Periodic Transaction Reports / PTRs)
   from multiple free sources, deduplicate and normalize them into a canonical schema.
2. **Score** members (and sectors) by historical, point-in-time–correct realized
   performance, filing timeliness, and conviction signals.
3. **Generate copy signals** for high-conviction *buys* with sizing scaled by
   member edge, disclosure freshness, and risk caps.
4. **Manage exits intelligently** without depending on the member's (late) sell
   filing — using profit targets, trailing stops, alpha-decay time limits, stop
   losses, and event-driven exits.
5. **Execute** on Alpaca, **paper by default**, live only on explicit human approval,
   mirroring the HawksTrade operational pattern (EC2 + systemd + AWS Secrets Manager).
6. **Backtest** copy strategies with strict point-in-time discipline (no lookahead).
7. **Report & monitor** via daily/weekly reports, health checks, and a read-only dashboard.
8. **Prove source eligibility** before implementation: every automated source must be
   free/non-paid, public, allowed by its terms, and documented in a source registry.

### 1.2 Non-Goals
- Not investment advice; this is a personal research/automation system.
- No use of non-public or paid data feeds. **Free sources only.**
- No high-frequency or intraday scalping — this is a swing/position copy system.
- No options *writing/selling-to-open* in v1 (long options only; see §6.4).
- No attempt to predict undisclosed trades — only acts on filed, public data.
- No scraping private/undocumented third-party APIs, bypassing access controls, or
  relying on expiring trials. Public UI sites such as CapitolTrades are research
  references unless a durable free API and acceptable terms are verified.

### 1.3 Guardrails (inherited from HawksTrade conventions)
- **Paper First.** `mode` never switches to `live` without an explicit human command
  in the current session.
- **Risk Integrity.** Stop-loss, profit-target, and position-sizing logic are not
  changed without explicit approval.
- **Credential Safety.** API keys are never printed or logged; secrets live in AWS
  Secrets Manager and are materialized to tmpfs (`/dev/shm`) at boot.
- **Live Remote Deployments.** Only `origin/main` is deployed to live; no ad-hoc
  branches/commits without approval.
- **Free Source Gate.** An adapter cannot be enabled for production unless
  `config/source_registry.yaml` marks it as `cost: free`, `terms_reviewed: true`, and
  `automated_access_allowed: true`.
- **Fail Closed.** When data freshness, source integrity, or regime checks cannot be
  verified, the engine blocks *new entries* but still allows protective *exits*.

### 1.4 Legal / Ethical Note
Congressional disclosures published under the **STOCK Act (2012)** are public-domain
government records. Copying publicly disclosed trades is legal, but the data is
**stale by design** (see §3). The system must surface this latency everywhere and must
never represent itself as having an informational edge over the public filing. Scraping
of official sites must respect each site's terms and use polite rate limiting. Third-party
sites must not be scraped unless their terms explicitly permit automated access.

---

## 2. The Core Challenge: Disclosure Latency

This single fact drives most of the design.

Under the STOCK Act, members must file a **Periodic Transaction Report (PTR)** within
**30 days of being notified** of a transaction, and **no later than 45 days** after the
transaction itself. Reportable transactions are purchases/sales/exchanges of **> $1,000**
of a covered security. Amounts are disclosed only as **ranges** (e.g. $1,001–$15,000;
$15,001–$50,000; … up to $50M+), never exact figures.

Consequences the architecture must handle:

| Reality | Architectural response |
|---|---|
| A buy you see today may have happened up to **45 days ago** (often more after publishing/parsing delay). | Model an **alpha-decay curve** from *transaction date*; discount or skip signals that are too stale. |
| You will see a member's **sell** just as late — too late to mirror. | **Never** wait for the sell filing. Run an **independent intelligent-sell engine** (§5). |
| Amounts are **ranges**, not exact. | Normalize to a `amount_min`/`amount_max`/`amount_mid`; size by *conviction*, not by mirroring dollar amounts. |
| **ETFs / mutual funds are generally exempt** from PTRs (only annual disclosure). | Expect equity *single-name* trades to dominate; treat ETF signals as sparse/low-priority. |
| Filings get **amended**; PDFs are sometimes handwritten/scanned. | Idempotent ingestion with amendment supersession + OCR fallback + parse-confidence scoring. |
| Backtests can easily "cheat" by using transaction dates. | Enforce **point-in-time**: a signal is only knowable on its **filing/publish date**, not its transaction date. |

---

## 3. Data Sources (Free Only)

Per decision, HawksCapitol uses **official filings as the source of truth** with **free
third-party APIs as a freshness/convenience fallback**. All adapters implement a common
`DisclosureSource` interface (§7.3) so sources are hot-swappable and cross-validated.

### 3.1 Primary — Official Government Filings (authoritative, public domain)

**House of Representatives — Clerk bulk data (preferred; cleanest bulk access)**
- Yearly ZIP index: `https://disclosures-clerk.house.gov/public_disc/financial-pdfs/<YEAR>FD.zip`
  containing `<YEAR>FD.xml` — one row per disclosure with `DocID`, `FilingType`,
  member name, state, year. Filter `FilingType=P` for PTRs.
- Per-filing PDF: `https://disclosures-clerk.house.gov/public_disc/ptr-pdfs/<YEAR>/<DocID>.pdf`
- The Clerk republishes a **fresh ZIP daily**. Public domain.
- Parsing: PDFs (mostly text-based "electronic" filings; some scanned → OCR fallback).

**Senate — Electronic Financial Disclosure (eFD)**
- Search portal: `https://efdsearch.senate.gov/search/`
- Flow: GET the landing page → accept the agreement (sets a session cookie) → obtain
  the CSRF token → `POST` to the search endpoint → receive JSON rows of filings →
  fetch each electronic PTR (structured HTML) or paper PTR (PDF → OCR).
- Requires a respectful, cookie+CSRF-aware client and gentle rate limiting.

### 3.2 Source Eligibility Policy
Before an adapter is used by scheduled jobs, it must be recorded in
`config/source_registry.yaml` and rendered into `docs/sources.md` with:
- source owner, URL, endpoint family, and whether it is official or third-party;
- cost status (`free`, `free_key`, `paid`, `unknown`) and any request limits;
- terms URL, date reviewed, and whether automated access is allowed;
- data license / reuse notes;
- production status (`enabled`, `disabled`, `manual_reference`, `history_only`).

Production jobs may enable only sources with `cost ∈ {free, free_key}` and
`automated_access_allowed: true`. Sources marked `paid`, `unknown`, or
`manual_reference` are blocked by config validation.

### 3.3 Fallback / Cross-check — Free Third-Party APIs
Used to (a) get faster notice of new filings, (b) cross-validate parses, and (c)
backfill when an official endpoint is temporarily unavailable. Treated as **untrusted**:
every record is reconciled against, and ultimately superseded by, the official filing.

| Source | Status | Notes |
|---|---|---|
| **Financial Modeling Prep (FMP)** | Optional `free_key` adapter if the active plan permits the congressional endpoints at no cost. | Structured JSON can help recency; adapter must degrade to disabled if quota, entitlement, or endpoint access fails. |
| **CongressInvests** | Optional `free_key` adapter if current free request limits and terms allow automated use. | Useful as a cross-check because it states it sources from Senate eFD + House Clerk; official filings still win. |
| **CapitolTrades.com** | `manual_reference` by default. | Good human-facing example/UX reference, but not a production source unless a free, documented API and acceptable terms are verified. |
| **Finnhub congressional trading** | `disabled` by default. | Current docs/search results mark the endpoint as premium; do not use unless a future free/non-paid entitlement is verified and recorded. |

### 3.4 Historical / Backtest Bulk (one-time + periodic refresh)
- **senate-stock-watcher** (GitHub) `all_transactions.json` — bulk historical Senate
  PTRs for backtesting. Update cadence is unreliable in 2026, so use it for **history**
  only if license/reuse terms are acceptable; never for live operation.
- House historical: derive from the Clerk yearly ZIPs (2014→present).

### 3.5 Auxiliary Official Data
- **Committee assignments:** prefer official House Clerk member XML / committee lists,
  Senate XML sources, and/or Congress.gov API committee endpoints for member-sector
  relevance. Cache snapshots by `as_of_date` so backtests do not use future committee
  assignments.
- **Member identity:** use Bioguide IDs where possible; maintain alias overlays for
  name variants, spouse/dependent owner fields, chamber changes, retirements, and
  candidates.

### 3.6 Market Data (prices, for sizing/exits/backtests — free)
- **Alpaca Market Data** (already used by HawksTrade) for quotes/bars on equities &
  options (entitlements permitting); primary because the broker is Alpaca. Delayed/IEX
  data is acceptable for paper/backtests if the limitation is recorded.
- **yfinance / Stooq** as free fallback for EOD history and corporate-action–adjusted
  prices in backtests, subject to their current terms and reliability.
- A **ticker/issuer resolver** maps disclosed asset names (free-text, e.g. "Apple Inc.")
  to tradeable symbols, handling renames, delistings, and splits.

### 3.7 Source Trust & Reconciliation
1. Ingest from all enabled sources into a raw store (append-only).
2. Normalize → canonical `Disclosure`/`Transaction` records.
3. **Deduplicate** by `(member_id, asset, tx_type, tx_date, amount_range)` with fuzzy
   matching; collapse amendments by `DocID` lineage (latest supersedes).
4. **Reconcile**: when an official record and an API record disagree, the **official**
   record wins; log the discrepancy with a `parse_confidence` score.
5. **Actability gate**: low-confidence, third-party-only, stale, or unresolved records
   can appear in reports/analytics, but cannot trigger live or paper entries until they
   are official or explicitly allowed by config.

---

## 4. Canonical Data Model

Persistence mirrors HawksTrade: **CSV/JSON under `data/` and `reports/`** (no external
DB required for v1; the schema is DB-ready if scale demands it later).

```
Member
  member_id            # stable internal id
  full_name, chamber   # "senate" | "house"
  party, state
  committees[]         # e.g. ["Armed Services", "Finance"] — for sector-relevance scoring
  aliases[]            # name variants seen across sources

Disclosure (one filed PTR document)
  doc_id, source       # "house_clerk" | "senate_efd" | "fmp" | "finnhub" | ...
  member_id
  filing_date          # date the document became public  <-- point-in-time anchor
  ingested_at
  url, parse_confidence
  amends_doc_id        # nullable; supersession lineage

Transaction (one line item within a disclosure)
  tx_id
  doc_id, member_id
  asset_name_raw       # as disclosed
  ticker               # resolved; nullable if unresolvable
  asset_type           # "stock" | "etf" | "option" | "bond" | "other"
  option_meta          # nullable: {right: call|put, strike, expiry} when disclosed
  tx_type              # "buy" | "sell" | "exchange" | "partial_sell"
  tx_date              # actual transaction date (for decay math only, NOT for PIT)
  filing_lag_days      # filing_date - tx_date; surfaced in every signal/report
  amount_min, amount_max, amount_mid
  owner                # self | spouse | joint | dependent
  dedup_key, raw_ref
  source_quality       # official | third_party_verified | third_party_only
  price_on_tx_date, price_on_filing_date
  filing_gap_pct       # price move between tx_date and filing_date

Signal (engine output)
  signal_id, created_at
  ticker, asset_type, side             # "copy_buy" | "exit"
  source_tx_ids[]                      # provenance
  conviction_score, freshness_score, entry_quality_score
  target_weight_pct                    # post-risk-cap sizing
  rationale                            # human-readable explanation
  blocked_reason                       # nullable; report why candidates were skipped

Position / Trade-log (broker truth, reused from HawksTrade conventions)
  trade_id, ticker, asset_type
  entry_date, entry_price, qty
  stop_price, target_price, trail_high
  copy_basis_tx_ids[], member_ids[]
  status, exit_date, exit_price, realized_pnl, exit_reason

MemberScore (rolling, point-in-time)
  member_id, as_of_date
  n_trades, hit_rate, avg_alpha_30d/90d, median_hold
  filing_latency_days, sector_concentration, sample_quality, score

SourceRegistry / SourceHealth
  source, owner, url, official, cost, terms_reviewed_at
  automated_access_allowed, production_status, rate_limit
  last_success_at, newest_filing_date, error_rate, freshness_state
```

---

## 5. The Intelligent Sell Engine (Exit Logic)

**Premise:** the member's own sell signal arrives too late to be useful. HawksCapitol
therefore owns its exits. Every open copy-position is evaluated on each scan by an
ordered set of exit rules; the **first** triggered rule wins. All thresholds live in
`config.yaml` and are risk-integrity protected.

Exit triggers (evaluated in priority order):

1. **Hard stop-loss** — price ≤ entry × (1 − `stop_loss_pct`) (ATR-scaled variant
   available, reusing HawksTrade's ATR stop module). Always active, even when entries
   are blocked.
2. **Profit target** — price ≥ entry × (1 + `take_profit_pct`). Optionally scale-out
   (sell ½ at target, trail the rest).
3. **Trailing stop / high-water** — once gain ≥ `trail_activation_pct`, exit if price
   falls `trailing_stop_pct` from the observed peak (mirrors HawksTrade
   `profit_trailing`).
4. **Alpha-decay time stop** — the central lag-aware rule. Define an *effective age* =
   `today − tx_date` (the disclosed *transaction* date, which may already be ~45 days
   old). If effective age ≥ `max_alpha_age_days` (configurable, e.g. 60), the
   informational edge is assumed exhausted → exit (flat or in profit) regardless of the
   hold clock. This is what replaces "wait for the member to sell."
5. **Event-driven exit** — exit if:
   - the same (or a correlated) member files a **sell** on the held name (late, but
     still a strong corroborating signal), or
   - a **sector regime** turn / broad-market regime gate flips red (reuse HawksTrade
     regime guards), or
   - an **earnings/corporate-action blackout** would expose the position to a known
     binary event beyond the system's risk appetite.
6. **Conviction-decay rebalance** — if the member's rolling `MemberScore` is revised
   sharply downward (e.g. a string of losing disclosed trades), trim/close positions
   that were opened primarily on that member's conviction.
7. **Max hold cap** — absolute backstop (e.g. `max_hold_days`) so nothing is held
   indefinitely.

**Options exits** add: time-to-expiry stop (close ≥ N days before expiry to avoid theta
cliff/assignment), and a delta/IV-aware profit target. v1 holds **long options only**, so
max loss is the premium.

> Design rule: exits are **fail-safe for protection**. New entries fail closed when
> source or market data is unhealthy. Open positions keep broker-side protective orders
> synchronized where possible; if local pricing is stale, the system uses the last known
> good price only for conservative risk decisions, raises a health alert, and never
> silently assumes the position is safe.

---

## 6. Signal Generation & Position Sizing

### 6.1 Member & Sector Scoring (point-in-time)
A nightly job computes, **using only data knowable as of each historical date**:
- **Hit rate** and **realized alpha** of each member's disclosed buys vs. SPY over
  30/90/180-day forward windows (computed on *closed* historical episodes only).
- **Filing timeliness** (median days between `tx_date` and `filing_date`) — faster
  filers give fresher, more actionable signals.
- **Committee/sector relevance** — trades in sectors overlapping a member's committee
  assignments are flagged (informational; **not** treated as illegal-edge inference).
- **Activity & concentration** — who is *actively* trading now, and how concentrated.
- **Sample quality** — minimum trade count, minimum recent disclosures, and confidence
  intervals; a member with one lucky trade should not outrank a durable pattern.
- Output: a normalized `score ∈ [0,1]` per member, and a sector-level aggregate
  identifying "hot" sectors by recent copyable buy flow and historical profitability.

### 6.2 Copy-Buy Decision
A disclosed **buy** becomes a candidate `copy_buy` when:
- `asset_type ∈ {stock, etf, option}` and the ticker resolves to a tradeable, liquid
  symbol (liquidity/ADV filter), **and**
- `freshness_score` (from alpha-decay curve on `tx_date`) ≥ threshold, **and**
- `entry_quality_score` passes: filing lag acceptable, price has not already run too
  far from `tx_date` to `filing_date`, no imminent earnings/corporate-action blackout,
  and parse/source confidence is high enough, **and**
- the originating member's (or aggregate sponsors') `score` ≥ threshold, **and**
- portfolio risk caps (§6.3) permit a new position.

Multiple members buying the same name within a window **stack conviction** (cluster
buys are the strongest signal).

### 6.3 Sizing & Risk Caps
- Base size targets a fixed **% account risk per trade** (ATR-based, reusing HawksTrade
  `atr_sizing`), **scaled** by `conviction_score × freshness_score`.
- Hard caps: `max_position_pct`, `max_positions`, **per-member exposure cap**,
  **per-sector exposure cap**, and a **correlation guard** (reuse HawksTrade
  `correlation_guard`) to avoid stacking correlated names.
- Portfolio gates: minimum cash buffer, max daily orders, max weekly turnover, max open
  risk, no averaging down, no shorting disclosed sells in v1, and no new entries when
  PDT/account restrictions or broker buying power could be violated.
- Disclosed dollar **ranges are NOT mirrored** — they only inform a coarse conviction
  tier (a $1M–$5M buy ranks above a $1k–$15k buy).
- `daily_loss_limit_pct` and an `order_governor` (rate/notional caps) bound execution,
  reused from HawksTrade.

### 6.4 Options Handling (v1)
- Disabled by default until parser, liquidity, and Alpaca options permissions are
  validated in paper.
- Act only on **clearly disclosed long calls/puts** with parseable strike/expiry; if
  option metadata is ambiguous, **fall back to a small delta-equivalent equity copy** or
  skip. No selling-to-open, no spreads in v1 (can integrate HawksOptions later).

---

## 7. Component Architecture

### 7.1 High-level flow
```
                         ┌──────────────────────────────────────────────┐
                         │              SOURCES (free/eligible)           │
   House Clerk ZIP/XML ──┤ Senate eFD │ optional free APIs │ history data │
                         └───────┬──────────────────────────────────────┘
                                 │  (DisclosureSource adapters, polite + cached)
                                 ▼
                        ┌──────────────────┐     append-only raw store (data/raw/)
                        │  INGESTION        │────────────────────────────────────►
                        │  fetch→parse→OCR  │
                        └────────┬─────────┘
                                 ▼
                        ┌──────────────────┐  canonical Members/Disclosures/Transactions
                        │ NORMALIZE +       │  dedupe • amend-supersede • ticker-resolve
                        │ RECONCILE         │  parse_confidence • reconciliation log
                        └────────┬─────────┘
                                 ▼
        ┌────────────────────────────────────────────────────────────────┐
        │  ANALYTICS                                                       │
        │  • MemberScore (PIT)  • Sector heatmap  • alpha-decay curves     │
        └────────┬───────────────────────────────────────────────────────┘
                 ▼
        ┌──────────────────┐        ┌───────────────────────────────────┐
        │ SIGNAL ENGINE     │        │  INTELLIGENT SELL ENGINE          │
        │ copy-buy candidates│◄──────┤  evaluates open positions (§5)    │
        │ sizing + risk caps │        └───────────────────────────────────┘
        └────────┬─────────┘
                 ▼
        ┌──────────────────┐   paper-first; live behind live_mode_guard
        │ EXECUTION (Alpaca)│   order_governor • broker_stops • reconcile
        └────────┬─────────┘
                 ▼
        ┌──────────────────┐
        │ REPORTING /       │   daily & weekly reports • health checks •
        │ DASHBOARD         │   read-only dashboard (Cloudflare tunnel)
        └──────────────────┘
```

### 7.2 Proposed repository layout (mirrors HawksTrade)
```
HawksCapitol/
├── AGENTS.md  SKILL.md                            # required local agent workflow files
├── CLAUDE.md / CODEX.md / GEMINI.md               # optional agent-specific mirrors
├── README.md  TESTING.md  requirements.txt  pyproject.toml
├── .gitignore  .beads/                            # local tracker enabled by bd init
├── config/
│   ├── config.yaml            # mode, thresholds, risk caps, sources toggles
│   ├── source_registry.yaml    # free-source eligibility + terms metadata
│   ├── sectors.json           # ticker→sector map (reuse HawksTrade)
│   ├── members.json           # committee/alias overlay (seed; auto-extended)
│   └── .env.example           # API keys (Alpaca; optional free API keys only)
├── docs/
│   ├── sources.md             # rendered source eligibility and terms notes
│   └── scoring.md             # score formulas, PIT invariants, validation gates
├── sources/                   # DisclosureSource adapters
│   ├── base.py                # DisclosureSource interface
│   ├── house_clerk.py  senate_efd.py  fmp.py  finnhub.py  stock_watcher.py
│   └── ticker_resolver.py
├── ingestion/
│   ├── fetcher.py  pdf_parser.py  ocr.py  normalizer.py  reconciler.py  dedupe.py
├── core/                      # reused/ported from HawksTrade where possible
│   ├── alpaca_client.py  broker_interface.py  order_executor.py  order_governor.py
│   ├── risk_manager.py  correlation_guard.py  atr_sizing.py  portfolio.py
│   ├── exit_policy.py  protection_manager.py  live_mode_guard.py
│   ├── config_loader.py  logging_config.py  trading_models.py  version.py
├── analytics/
│   ├── member_score.py  sector_heatmap.py  alpha_decay.py
├── engine/
│   ├── copy_signal.py         # buy-candidate generation
│   ├── sell_engine.py         # §5 intelligent exits
│   └── conviction.py
├── backtest/
│   ├── pit_replay.py          # point-in-time disclosure replay
│   ├── simulator.py  metrics.py
├── scheduler/                 # entrypoints invoked by systemd timers
│   ├── run_ingest.py  run_score.py  run_scan.py  run_risk_check.py
│   ├── run_report.py  run_backtest.py  run_health_check.py  reconcile_trade_log.py
│   ├── systemd/   launchd/   cron/    # unit + timer files per platform
├── scripts/
│   ├── fetch_secrets.sh       # AWS Secrets Manager → /dev/shm/.hawkscapitol.env
│   └── seed_history.py
├── dashboard/                 # read-only Flask status UI + Cloudflare tunnel
├── data/  (raw/ canonical/ universe/ archive/)   reports/  logs/
└── tests/
```

### 7.3 Key interfaces
```python
class DisclosureSource(Protocol):
    name: str
    def fetch(self, since: date) -> list[RawFiling]: ...     # network + cache
    def parse(self, raw: RawFiling) -> list[Transaction]: ... # → canonical
    def health(self) -> SourceHealth: ...                     # for fail-closed checks

class ExitRule(Protocol):
    priority: int
    def evaluate(self, pos: Position, mkt: MarketSnapshot, cfg) -> ExitDecision | None: ...

class Broker(Protocol):              # Alpaca impl; paper/live via base_url + guard
    def submit(self, order: Order) -> OrderResult: ...
    def positions(self) -> list[BrokerPosition]: ...
    def reconcile(self, trade_log) -> ReconcileReport: ...
```

---

## 8. Operations (mirrors HawksTrade exactly)

### 8.1 Stack
- **OS:** Amazon Linux 2023 (EC2) · **Language:** Python 3.10+
- **Scheduler:** systemd services + timers (cron/launchd provided for dev parity)
- **Secrets:** AWS Secrets Manager → materialized to **tmpfs `/dev/shm/.hawkscapitol.env`**
  at boot by `scripts/fetch_secrets.sh`; `HAWKSCAPITOL_REQUIRE_SHM=1` fails closed in prod.
- **Persistence:** CSV/JSON in `data/` and `reports/`.
- **Broker:** Alpaca (`alpaca-py`), paper and live endpoints.

### 8.2 Instance aliases (extends the HawksTrade deploy table)
| Alias | Target |
|---|---|
| `HCEC2P` | HawksCapitol EC2 **Paper** |
| `HCEC2L` | HawksCapitol EC2 **Live** |

The `deploy <instance>` workflow, status/log commands, and verification requirements
follow the operations root `CLAUDE.md` verbatim (resolve alias → inspect remote →
deploy `origin/main` only → align systemd units → daemon-reload → validate → monitor
≥10 min). Live deploys are `origin/main` only.

### 8.3 Scheduled jobs (systemd timers, prefix `hawkscapitol-*`)
| Timer | Cadence (suggested) | Job |
|---|---|---|
| `hawkscapitol-ingest` | every 1–3 h (market days + nightly) | pull new filings from all sources, normalize, reconcile |
| `hawkscapitol-score` | nightly | recompute MemberScore + sector heatmap (PIT) |
| `hawkscapitol-scan` | a few times/day during market hours | generate copy-buy signals + place entries (paper) |
| `hawkscapitol-risk-check` | every ~15 min during market hours | run intelligent-sell engine on open positions |
| `hawkscapitol-daily-report` | after close | P&L, new signals, exits, source-health digest |
| `hawkscapitol-weekly-report` | weekly | member/sector performance review |
| `hawkscapitol-health-check` | every ~10 min | source freshness, broker reachability, stale-data alarms |
| `hawkscapitol-secrets` | at boot (oneshot) | populate `/dev/shm/.hawkscapitol.env` |

Secrets job ordered `Before` all trading jobs; trading jobs `Requires`/`After` secrets
+ network-online (same ordering discipline as HawksTrade).

### 8.4 Verification (before any task is "Done")
1. `python3 -m unittest discover -v` green.
2. Relevant scheduler script runs clean with `--dry-run` (no orders placed).
3. `/dev/shm/.hawkscapitol.env` present if secrets touched.
4. No new errors in `journalctl`.
5. On any remote (paper/live) change: validate services, timers, dry-runs/health, logs.

### 8.5 Workflow / tracking (Beads)
New repo gets its own Beads tracker. Per operations-root routing: changes inside
`HawksCapitol/` update the HawksCapitol tracker; operations-only EC2 interventions with
no repo file changes update the HawksTradeOperations tracker.

Local Beads is initialized with prefix `HawksCapitol`. Agents must run `bd` from this
directory for code, docs, tests, and deployment files changed inside this project.

### 8.6 Remote Repository
The git remote is `https://github.com/aruc-dev/HawksCapitol.git`. Verify it from
`HawksCapitol/` with `git remote -v` before pushing or deploying. Keep live deployments
restricted to approved `origin/main`.

---

## 9. Cross-Cutting Concerns

- **Point-in-time correctness** — the single most important backtest invariant: a
  disclosure is only visible from its `filing_date`. `backtest/pit_replay.py` enforces
  this; any analytics that touch `tx_date` for visibility are a bug.
- **Idempotency** — re-running ingest never double-counts; everything keyed by
  `doc_id`/`dedup_key`; amendments supersede via `amends_doc_id`.
- **Corporate actions** — splits/symbol changes handled in `ticker_resolver` and in
  backtest price adjustment; delisted names are skipped for entries, force-exited if held.
- **Liquidity** — ADV/spread filter blocks illiquid microcaps that members sometimes hold.
- **Observability** — structured logs (no secrets), per-source health metrics, signal
  provenance (`source_tx_ids`) on every trade for auditability.
- **Polite scraping** — caching, backoff, conditional GETs, and per-source rate limits;
  respect site terms; identify a contact UA. Official bulk endpoints (House ZIP) are
  preferred over per-page scraping.
- **Data retention** — append-only raw store + archived canonical snapshots enable
  reproducible backtests and post-hoc audits.
- **Source compliance** — source registry validation blocks paid/unknown/unauthorized
  endpoints; third-party sites remain manual references until approved.
- **Decision explainability** — every candidate receives a rationale and a
  `blocked_reason` so skipped trades are as auditable as executed trades.
- **Security** — least-privilege IAM (read-only Secrets Manager, scoped to
  `hawkscapitol/*`), tmpfs secrets, never logging keys, read-only dashboard behind a
  tunnel.

---

## 10. Key Design Decisions (summary)

| Decision | Choice | Why |
|---|---|---|
| Execution model | **Auto-trade, paper-first** (HCEC2P/HCEC2L) | Mirrors HawksTrade; safe validation path before live. |
| Data sources | **Official filings (truth) + free APIs (fallback)** | Authoritative + fresh; fully free; cross-validated. |
| Asset scope | **Stocks, ETFs, + long options** | Matches the bulk of copyable disclosures; ties into HawksOptions later. |
| Exits | **Independent intelligent-sell engine** | Member sell filings are too late to mirror. |
| Sizing | **Conviction × freshness, ATR risk, ranges not mirrored** | Disclosed amounts are coarse ranges, not actionable dollar figures. |
| Storage | **CSV/JSON files** | Matches Hawks family; DB-ready schema if scale demands. |
| Ops | **EC2 + systemd + AWS Secrets Manager + tmpfs** | Identical to HawksTrade for operational consistency. |

---

## 11. Risks & Open Questions

- **Source fragility / paid drift** — official portals change markup / add anti-bot
  measures, and free API tiers can become paid. *Mitigation:* official filings are the
  truth, optional APIs are disabled unless source-registry validation passes, and any
  single source can fail without halting exits.
- **Edge reality** — published research is mixed on whether copying congressional trades
  beats the index *after* the ~45-day lag. *Mitigation:* the backtest harness and
  MemberScore exist precisely to validate (or refute) edge before any live capital; keep
  it paper until evidence supports promotion.
- **OCR accuracy** on handwritten/scanned filings — *Mitigation:* parse-confidence
  gating; low-confidence records inform analytics but don't trigger trades.
- **Chasing already-priced moves** — many trades will be public only after the market
  has moved. *Mitigation:* entry-quality and filing-gap filters block stale/FOMO entries.
- **ETF sparsity** — ETFs largely exempt from PTRs, so ETF copy signals will be thin.
- **Open items for the user:** target account size & per-trade risk %; live-promotion
  criteria (min backtested Sharpe / sample size); notification channel (email/Slack);
  whether to also short on disclosed sells (default: **no** in v1).
