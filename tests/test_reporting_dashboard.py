from __future__ import annotations

import json
import unittest
from datetime import date
from pathlib import Path
import tempfile

from broker.paper_broker import PaperBroker
from core.models import Order
from dashboard import app as dashboard_app
from dashboard.app import render_dashboard_html
from ingestion.storage import read_json, write_json
from scheduler import run_health_check, run_report, run_weekly_report


class ReportingDashboardTests(unittest.TestCase):
    def test_health_check_reports_enabled_sources_and_json_safe_dates(self) -> None:
        payload = run_health_check.run(dry_run=True, as_of=date(2026, 6, 8))

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["mode"], "paper")
        self.assertEqual(payload["source_status"]["house_clerk"]["newest_filing_date"], "2026-06-03")
        self.assertEqual(payload["source_status"]["senate_efd"]["newest_filing_date"], "2026-06-02")
        json.dumps(payload)

    def test_health_check_flags_stale_enabled_sources(self) -> None:
        payload = run_health_check.run(dry_run=True, as_of=date(2026, 6, 20))

        stale_sources = {alert["source"] for alert in payload["alerts"] if alert["reason"] == "source_stale"}
        self.assertIn("house_clerk", stale_sources)
        self.assertIn("senate_efd", stale_sources)
        self.assertTrue(payload["ok"])

    def test_health_check_skips_malformed_filing_dates(self) -> None:
        cfg = run_health_check.load_config()
        registry = run_health_check.load_source_registry(cfg["source_registry_path"])
        transactions = [
            {"source": "house_clerk", "filing_date": "not-a-date"},
            {"source": "house_clerk", "filing_date": "2026-06-04"},
            {"source": "senate_efd", "filing_date": "bad-date"},
        ]

        status = run_health_check._source_status(cfg, registry, transactions, date(2026, 6, 8))

        self.assertEqual(status["house_clerk"]["newest_filing_date"], "2026-06-04")
        self.assertEqual(status["house_clerk"]["row_count"], 2)
        self.assertIsNone(status["senate_efd"]["newest_filing_date"])

    def test_health_check_flags_low_parse_confidence(self) -> None:
        cfg = run_health_check.load_config()
        registry = run_health_check.load_source_registry(cfg["source_registry_path"])
        transactions = [
            {"source": "house_clerk", "filing_date": "2026-06-04", "parse_confidence": 0.5},
            {"source": "house_clerk", "filing_date": "2026-06-05", "parse_confidence": 0.95},
        ]

        status = run_health_check._source_status(cfg, registry, transactions, date(2026, 6, 8))
        alerts = run_health_check._alerts(status, cfg)

        self.assertEqual(status["house_clerk"]["low_parse_confidence_count"], 1)
        self.assertIn(
            {
                "severity": "warning",
                "source": "house_clerk",
                "reason": "low_parse_confidence",
                "count": 1,
                "min_parse_confidence": cfg["health"]["min_parse_confidence"],
            },
            alerts,
        )

    def test_health_check_reads_paper_broker_from_configured_data_dir(self) -> None:
        original_load_config = run_health_check.load_config
        try:
            with tempfile.TemporaryDirectory() as tmp:
                cfg = original_load_config()
                cfg["data_dir"] = str(Path(tmp) / "custom-data")
                state_path = Path(cfg["data_dir"]) / "paper_broker" / "state.json"
                PaperBroker(state_path).submit(Order("health-state", "AAPL", "buy", 3, limit_price=100.0))
                run_health_check.load_config = lambda: cfg

                payload = run_health_check.run(dry_run=True, as_of=date(2026, 6, 8))

                self.assertEqual(payload["broker"]["positions"][0]["ticker"], "AAPL")
        finally:
            run_health_check.load_config = original_load_config

    def test_health_check_corrupt_canonical_transactions_fails_closed(self) -> None:
        original_load_config = run_health_check.load_config
        try:
            with tempfile.TemporaryDirectory() as tmp:
                cfg = original_load_config()
                cfg["data_dir"] = str(Path(tmp) / "runtime-data")
                transactions_path = Path(cfg["data_dir"]) / "canonical" / "transactions.json"
                transactions_path.parent.mkdir(parents=True)
                transactions_path.write_text("{bad json", encoding="utf-8")
                run_health_check.load_config = lambda: cfg

                payload = run_health_check.run(dry_run=False, as_of=date(2026, 6, 8))

                self.assertTrue(payload["ok"])
                self.assertEqual(payload["source_status"]["house_clerk"]["row_count"], 0)
                self.assertEqual(payload["source_status"]["senate_efd"]["row_count"], 0)
        finally:
            run_health_check.load_config = original_load_config

    def test_daily_report_and_dashboard_render_without_flask(self) -> None:
        report = run_report.run(dry_run=True)

        self.assertIn("health", report)
        self.assertGreaterEqual(report["summary"]["signals"], 1)
        json.dumps(report)
        html = render_dashboard_html(report)
        self.assertIn("HawksCapitol Dashboard", html)
        self.assertIn("Signals", html)
        self.assertIn("Sources", html)
        self.assertIn("house_clerk", html)

    def test_dashboard_default_uses_persisted_report_mode(self) -> None:
        original_run_report = dashboard_app.run_report
        calls = []
        report = {
            "summary": {"signals": 0, "backtest_verdict": "not_available", "health_ok": True},
            "scan": {"signals": []},
            "health": {"source_status": {}, "alerts": []},
        }
        try:
            dashboard_app.run_report = lambda dry_run=False: calls.append(dry_run) or report

            html = dashboard_app.render_dashboard_html()
            preview_html = dashboard_app.render_dashboard_html(dry_run=True)

            self.assertEqual(calls, [False, True])
            self.assertIn("not_available", html)
            self.assertIn("not_available", preview_html)
        finally:
            dashboard_app.run_report = original_run_report

    def test_reports_use_configured_reports_dir(self) -> None:
        original_daily_load_config = run_report.load_config
        original_weekly_load_config = run_weekly_report.load_config
        original_daily_health = run_report.run_health
        try:
            with tempfile.TemporaryDirectory() as tmp:
                cfg = original_daily_load_config()
                cfg["reports_dir"] = str(Path(tmp) / "custom-reports")
                run_report.load_config = lambda: cfg
                run_weekly_report.load_config = lambda: cfg
                run_report.run_health = lambda dry_run=False: {"ok": True, "alerts": []}

                run_report.run(dry_run=False)
                run_weekly_report.run(dry_run=False)

                self.assertTrue((Path(cfg["reports_dir"]) / "daily" / "latest.json").exists())
                self.assertTrue((Path(cfg["reports_dir"]) / "weekly" / "latest.json").exists())
        finally:
            run_report.load_config = original_daily_load_config
            run_weekly_report.load_config = original_weekly_load_config
            run_report.run_health = original_daily_health

    def test_non_dry_daily_report_reads_persisted_runtime_artifacts(self) -> None:
        original_load_config = run_report.load_config
        original_scan = run_report.run_scan_report
        original_backtest = run_report.run_backtest_report
        original_risk = run_report.run_risk
        original_health = run_report.run_health
        health_calls = []

        def forbidden_runner(*_args, **_kwargs):
            raise AssertionError("non-dry report should not invoke sample-producing runners")

        try:
            with tempfile.TemporaryDirectory() as tmp:
                cfg = original_load_config()
                cfg["data_dir"] = str(Path(tmp) / "runtime-data")
                cfg["reports_dir"] = str(Path(tmp) / "runtime-reports")
                report_dir = Path(cfg["reports_dir"])
                data_dir = Path(cfg["data_dir"])
                write_json(data_dir / "signals" / "latest.json", [{"signal_id": "real-signal", "blocked_reason": None}])
                write_json(data_dir / "trade_log.json", [{"client_order_id": "real-order"}])
                write_json(report_dir / "backtest" / "latest.json", {"validation": {"verdict": "pass"}, "metrics": {"trade_count": 2, "per_member": {"m1": 1}, "per_sector": {"Technology": 1}}})
                write_json(report_dir / "risk_decisions.json", [{"ticker": "AAPL", "reason": "profit_target"}])
                run_report.load_config = lambda: cfg
                run_report.run_scan_report = forbidden_runner
                run_report.run_backtest_report = forbidden_runner
                run_report.run_risk = forbidden_runner
                run_report.run_health = lambda dry_run=False: health_calls.append(dry_run) or {"ok": True, "alerts": []}

                report = run_report.run(dry_run=False)

                self.assertEqual(report["summary"]["signals"], 1)
                self.assertEqual(report["summary"]["backtest_verdict"], "pass")
                self.assertEqual(report["summary"]["risk_decisions"], 1)
                self.assertEqual(report["scan"]["signals"][0]["signal_id"], "real-signal")
                self.assertEqual(health_calls, [False])
                self.assertEqual(read_json(report_dir / "daily" / "latest.json")["scan"]["accepted_orders"][0]["client_order_id"], "real-order")
        finally:
            run_report.load_config = original_load_config
            run_report.run_scan_report = original_scan
            run_report.run_backtest_report = original_backtest
            run_report.run_risk = original_risk
            run_report.run_health = original_health

    def test_non_dry_daily_report_corrupt_persisted_artifacts_fail_closed(self) -> None:
        original_load_config = run_report.load_config
        original_scan = run_report.run_scan_report
        original_backtest = run_report.run_backtest_report
        original_risk = run_report.run_risk
        original_health = run_report.run_health

        def forbidden_runner(*_args, **_kwargs):
            raise AssertionError("non-dry report should not invoke sample-producing runners")

        try:
            with tempfile.TemporaryDirectory() as tmp:
                cfg = original_load_config()
                cfg["data_dir"] = str(Path(tmp) / "runtime-data")
                cfg["reports_dir"] = str(Path(tmp) / "runtime-reports")
                data_dir = Path(cfg["data_dir"])
                report_dir = Path(cfg["reports_dir"])
                for path in (
                    data_dir / "signals" / "latest.json",
                    data_dir / "trade_log.json",
                    report_dir / "backtest" / "latest.json",
                    report_dir / "risk_decisions.json",
                ):
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text("{bad json", encoding="utf-8")
                run_report.load_config = lambda: cfg
                run_report.run_scan_report = forbidden_runner
                run_report.run_backtest_report = forbidden_runner
                run_report.run_risk = forbidden_runner
                run_report.run_health = lambda dry_run=False: {"ok": True, "alerts": []}

                report = run_report.run(dry_run=False)

                self.assertEqual(report["summary"]["signals"], 0)
                self.assertEqual(report["summary"]["backtest_verdict"], "not_available")
                self.assertEqual(report["summary"]["risk_decisions"], 0)
                self.assertEqual(report["scan"], {"signals": [], "accepted_orders": []})
        finally:
            run_report.load_config = original_load_config
            run_report.run_scan_report = original_scan
            run_report.run_backtest_report = original_backtest
            run_report.run_risk = original_risk
            run_report.run_health = original_health

    def test_non_dry_weekly_report_reuses_persisted_daily_report(self) -> None:
        original_daily_report = run_weekly_report.run_daily_report
        try:
            with tempfile.TemporaryDirectory() as tmp:
                report_dir = Path(tmp) / "runtime-reports"
                daily = {
                    "summary": {"signals": 4, "backtest_verdict": "pass", "health_ok": True},
                    "backtest": {"metrics": {"trade_count": 3, "per_member": {"m1": 2}, "per_sector": {"Technology": 3}}},
                }
                write_json(report_dir / "daily" / "latest.json", daily)
                run_weekly_report.run_daily_report = lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("weekly should read persisted daily report"))

                weekly = run_weekly_report.run(dry_run=False, reports_dir=report_dir)

                self.assertEqual(weekly["summary"]["signals"], 4)
                self.assertEqual(weekly["summary"]["trade_count"], 3)
                self.assertEqual(weekly["latest_daily_report"], daily)
                self.assertEqual(read_json(report_dir / "weekly" / "latest.json")["member_performance"], {"m1": 2})
        finally:
            run_weekly_report.run_daily_report = original_daily_report

    def test_non_dry_weekly_report_corrupt_daily_regenerates(self) -> None:
        original_daily_report = run_weekly_report.run_daily_report
        try:
            with tempfile.TemporaryDirectory() as tmp:
                report_dir = Path(tmp) / "runtime-reports"
                daily_path = report_dir / "daily" / "latest.json"
                daily_path.parent.mkdir(parents=True)
                daily_path.write_text("{bad json", encoding="utf-8")
                regenerated = {
                    "summary": {"signals": 1, "backtest_verdict": "watch", "health_ok": True},
                    "backtest": {"metrics": {"trade_count": 1, "per_member": {}, "per_sector": {}}},
                }
                calls = []

                def regenerate(dry_run=False, reports_dir=None):
                    calls.append((dry_run, reports_dir))
                    return regenerated

                run_weekly_report.run_daily_report = regenerate

                weekly = run_weekly_report.run(dry_run=False, reports_dir=report_dir)

                self.assertEqual(calls, [(False, report_dir)])
                self.assertEqual(weekly["latest_daily_report"], regenerated)
                self.assertEqual(weekly["summary"]["signals"], 1)
        finally:
            run_weekly_report.run_daily_report = original_daily_report


if __name__ == "__main__":
    unittest.main()
