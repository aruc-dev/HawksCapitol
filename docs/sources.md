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
