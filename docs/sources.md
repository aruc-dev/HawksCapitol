# Source Registry

Production source eligibility is defined in `config/source_registry.yaml`.

Rules:

- official House/Senate filings are source of truth;
- paid, unknown, manual-reference, or terms-unreviewed sources cannot be enabled for
  production;
- optional free-key APIs are untrusted cross-checks and must self-disable on quota or
  entitlement failures;
- CapitolTrades is a manual reference by default;
- Finnhub congressional trading is disabled by default because current docs mark it
  premium.

## Current Source Status

| Source | Owner | Cost | Automated access | Production status | Notes |
|---|---|---:|---:|---|---|
| `house_clerk` | U.S. House Office of the Clerk | free | yes | enabled | Official source of truth for House PTR ZIP/XML indexes and PTR PDFs. |
| `senate_efd` | U.S. Senate eFD | free | yes | enabled | Official source of truth for Senate PTR search rows, electronic reports, and PDFs. |
| `fmp` | Financial Modeling Prep | free_key | no | disabled | Optional adapter; remains disabled until terms/entitlement review confirms automated free use. |
| `congressinvests` | CongressInvests | free_key | no | disabled | Optional cross-check adapter; remains disabled until terms and limits are reviewed. |
| `capitoltrades_reference` | CapitolTrades | unknown | no | manual_reference | Human-facing reference only; no automated scraping. |
| `finnhub` | Finnhub | paid | no | disabled | Congressional endpoint is treated as paid/premium and cannot be enabled. |
| `stock_watcher` | senate-stock-watcher data | free | no | history_only | Historical fixture/backtest helper only; not a live source. |

Enabled production runs currently use only official House Clerk and Senate eFD sources.
Optional third-party adapters are fixture-tested but fail closed unless source-registry
policy allows them.
