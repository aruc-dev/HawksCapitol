from __future__ import annotations

from html import escape

from scheduler.run_report import run as run_report


def render_dashboard_html(report: dict | None = None, dry_run: bool = False) -> str:
    report = report if report is not None else run_report(dry_run=dry_run)
    source_rows = "".join(
        f"<tr><td>{escape(name)}</td><td>{status['enabled']}</td><td>{escape(status['production_status'])}</td><td>{status['newest_filing_date'] or ''}</td><td>{status['stale_days'] if status['stale_days'] is not None else ''}</td></tr>"
        for name, status in sorted(report["health"]["source_status"].items())
    )
    signal_rows = "".join(
        f"<tr><td>{escape(sig['ticker'])}</td><td>{sig['target_weight_pct']}</td><td>{escape(str(sig.get('blocked_reason') or ''))}</td></tr>"
        for sig in report["scan"]["signals"]
    )
    alert_rows = "".join(
        f"<li>{escape(alert['severity'])}: {escape(alert.get('source', 'system'))} {escape(alert['reason'])}</li>"
        for alert in report["health"]["alerts"]
    )
    return f"""<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>HawksCapitol Dashboard</title></head>
<body>
<h1>HawksCapitol Dashboard</h1>
<section><h2>Summary</h2><p>Signals: {report['summary']['signals']} | Verdict: {escape(report['summary']['backtest_verdict'])} | Health: {report['summary']['health_ok']}</p></section>
<section><h2>Signals</h2><table><tr><th>Ticker</th><th>Target Weight</th><th>Blocked Reason</th></tr>{signal_rows}</table></section>
<section><h2>Sources</h2><table><tr><th>Source</th><th>Enabled</th><th>Status</th><th>Newest Filing</th><th>Stale Days</th></tr>{source_rows}</table></section>
<section><h2>Alerts</h2><ul>{alert_rows}</ul></section>
</body></html>"""


def create_app():
    try:
        from flask import Flask
    except Exception as exc:
        raise RuntimeError("Flask is required to serve the dashboard; render_dashboard_html works without Flask") from exc
    app = Flask(__name__)

    @app.get("/")
    def index():
        return render_dashboard_html()

    return app


if __name__ == "__main__":
    create_app().run(host="127.0.0.1", port=8080)
