from __future__ import annotations

import json
import unittest
from datetime import date
from pathlib import Path
import tempfile

from broker.paper_broker import PaperBroker
from core.models import Order
from dashboard.app import render_dashboard_html
from scheduler import run_health_check, run_report


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


if __name__ == "__main__":
    unittest.main()
