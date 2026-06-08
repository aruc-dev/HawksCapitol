# Phase 10 Hardening Backlog

Phase 10 is ongoing work after the v1 paper system is deployable. These tracks are
intentionally blocked or deferred until the required paper evidence, source review, or
human approval exists.

| Track | Bead | Current gate | Required validation |
|---|---|---|---|
| HCEC2P remote deployment | `HawksCapitol-dxb` | Reviewed Terraform apply, paper secret value, and explicit paper deploy approval | Terraform outputs, remote `systemctl`, `/dev/shm` secrets validation, dry-runs, health, `journalctl`, 10-minute monitor |
| Paper results and score tuning | `HawksCapitol-3mn` | At least 4 weeks of HCEC2P paper history | Backtest plus paper before/after report, focused scoring tests, promotion gate rerun |
| Walk-forward revalidation | `HawksCapitol-6hl` | Paper deployment and report retention decision | No-lookahead tests, deterministic report fixtures, dry-run scheduler |
| Decayed-edge auto-disable | `HawksCapitol-88z` | Realized paper evidence and threshold approval | Advisory-only tests first, disable/reenable fixtures, audit trail checks |
| HawksOptions integration | `HawksCapitol-0al` | Stable paper deployment and integration scope approval | Paper-only contract tests, live guard tests, execution boundary review |
| Notifications | `HawksCapitol-7ud` | Approved provider/channel and secret provisioning | Dry-run notification tests, rate-limit tests, secret redaction checks |
| Official coverage expansion | `HawksCapitol-w62` | Reviewed official fixture/member scope | Fixture parser tests, alias tests, registry compliance, network-free CI |

Risk parameters, scoring weights, auto-disable thresholds, notification providers, and
optional integrations require explicit human approval before activation. Live remains
blocked by the live promotion gate and `live_mode_guard`.
