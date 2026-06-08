# Live Promotion Gate

HawksCapitol remains paper-first. The default config is `"mode": "paper"` and
`execution.allow_live` is `false`.

Live promotion requires all of the following:

1. Backtest validation verdict is `pass`.
2. At least 4 weeks of paper operation.
3. At least 20 paper trades.
4. Paper hit rate is at least 50%.
5. Paper max drawdown is no more than 8%.
6. Deployment source is approved `origin/main`.
7. A human explicitly approves live mode in the current session.

The gate is checked by:

```bash
python3 scheduler/run_live_promotion_check.py --dry-run
```

With `--dry-run`, the command uses the deterministic sample backtest only for local
scheduler validation. Without `--dry-run`, it reads the persisted real backtest report
from `<reports_dir>/backtest/latest.json`. Missing, malformed, sample-backed, or
fallback-return reports are treated as non-passing evidence and block live promotion.

Supplying paper evidence still does not switch modes:

```bash
python3 scheduler/run_live_promotion_check.py --dry-run \
  --paper-weeks 4 \
  --paper-trades 20 \
  --paper-hit-rate 0.55 \
  --paper-max-drawdown-pct 0.04
```

Even after the evidence gate passes, live orders remain blocked until a human explicitly
approves the session and the live config is changed intentionally. The runtime live guard
still requires both `execution.allow_live=true` and an in-session approval flag.

## HCEC2L Readiness

HCEC2L is the future live EC2 target. It is not activated by this repository state.

Required live setup, after approval only:

- Create a separate AWS Secrets Manager secret at `hawkscapitol/live/keys`.
- Keep paper credentials in `hawkscapitol/keys`; do not reuse paper secrets for live.
- Deploy approved `origin/main` only.
- Set `"mode": "live"` and `execution.allow_live=true` only on the approved live host.
- Run `python3 scheduler/run_live_promotion_check.py --dry-run` with paper evidence.
- Run a no-order validation pass before enabling any live scheduler.
- Enable live systemd timers only after human confirmation in the same session.

Remote validation must include `systemctl list-timers 'hawkscapitol-*'`, secrets
validation for `/dev/shm/.hawkscapitol.env`, scheduler dry-runs, health checks,
`journalctl` review, and at least 10 minutes of monitoring.
