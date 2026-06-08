from __future__ import annotations

import unittest

from scheduler import (
    reconcile_trade_log,
    run_backtest,
    run_health_check,
    run_ingest,
    run_live_promotion_check,
    run_report,
    run_risk_check,
    run_scan,
    run_score,
    run_weekly_report,
)


class SchedulerDryRunTests(unittest.TestCase):
    def test_all_scheduler_dry_runs_execute(self) -> None:
        self.assertGreaterEqual(run_ingest.run(dry_run=True)["transactions"], 1)
        self.assertTrue(run_score.run(dry_run=True)["member_scores"])
        self.assertIn("signals", run_scan.run(dry_run=True))
        self.assertIn("decisions", run_risk_check.run(dry_run=True))
        self.assertIn("metrics", run_backtest.run(dry_run=True))
        self.assertTrue(run_health_check.run(dry_run=True)["ok"])
        self.assertIn("scan", run_report.run(dry_run=True))
        self.assertEqual(run_weekly_report.run(dry_run=True)["period"], "weekly")
        self.assertFalse(run_live_promotion_check.run(dry_run=True)["eligible"])
        self.assertIn("missing_in_broker", reconcile_trade_log.run(dry_run=True))


if __name__ == "__main__":
    unittest.main()
