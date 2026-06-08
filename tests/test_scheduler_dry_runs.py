from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from core.config_loader import load_config
from ingestion.storage import write_json
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

    def test_live_promotion_non_dry_uses_persisted_backtest_verdict(self) -> None:
        original_load_config = run_live_promotion_check.load_config
        original_backtest_runner = run_live_promotion_check.run_backtest_report
        try:
            with tempfile.TemporaryDirectory() as tmp:
                cfg = load_config()
                cfg["reports_dir"] = tmp
                cfg["promotion"] = {**cfg["promotion"], "require_origin_main": False}
                run_live_promotion_check.load_config = lambda: cfg

                def forbidden_sample_runner(*args, **kwargs):
                    raise AssertionError("non-dry live promotion must not run sample backtests")

                run_live_promotion_check.run_backtest_report = forbidden_sample_runner
                write_json(
                    Path(tmp) / "backtest" / "latest.json",
                    {
                        "validation": {"verdict": "watch"},
                        "dataset": "data/backtest/official_house_6mo/transactions.json",
                        "price_history_dataset": "data/backtest/official_house_6mo/prices.json",
                        "market_data": {"price_history_supplied": True},
                    },
                )

                result = run_live_promotion_check.run(
                    dry_run=False,
                    paper_weeks=4,
                    paper_trades=20,
                    paper_hit_rate=0.55,
                    paper_max_drawdown_pct=0.04,
                    human_approved=True,
                )

                self.assertFalse(result["eligible"])
                self.assertEqual(result["evidence"]["backtest_verdict"], "watch")
                self.assertEqual(result["backtest"]["status"], "loaded")
                self.assertIn("backtest_verdict_not_passed", result["reasons"])
        finally:
            run_live_promotion_check.load_config = original_load_config
            run_live_promotion_check.run_backtest_report = original_backtest_runner

    def test_live_promotion_non_dry_missing_backtest_fails_closed(self) -> None:
        original_load_config = run_live_promotion_check.load_config
        original_backtest_runner = run_live_promotion_check.run_backtest_report
        try:
            with tempfile.TemporaryDirectory() as tmp:
                cfg = load_config()
                cfg["reports_dir"] = tmp
                cfg["promotion"] = {**cfg["promotion"], "require_origin_main": False}
                run_live_promotion_check.load_config = lambda: cfg
                run_live_promotion_check.run_backtest_report = lambda *args, **kwargs: self.fail(
                    "missing non-dry reports should fail closed without sample fallback"
                )

                result = run_live_promotion_check.run(
                    dry_run=False,
                    paper_weeks=4,
                    paper_trades=20,
                    paper_hit_rate=0.55,
                    paper_max_drawdown_pct=0.04,
                    human_approved=True,
                )

                self.assertFalse(result["eligible"])
                self.assertEqual(result["evidence"]["backtest_verdict"], "missing")
                self.assertEqual(result["backtest"]["status"], "missing_or_malformed")
                self.assertIn("backtest_verdict_not_passed", result["reasons"])
        finally:
            run_live_promotion_check.load_config = original_load_config
            run_live_promotion_check.run_backtest_report = original_backtest_runner


if __name__ == "__main__":
    unittest.main()
