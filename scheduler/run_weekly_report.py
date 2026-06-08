from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.config_loader import load_config
from core.serialization import to_jsonable
from ingestion.storage import read_json_safe, write_json
from scheduler.run_report import run as run_daily_report


def run(dry_run: bool = False, reports_dir: str | Path | None = None) -> dict:
    cfg = load_config()
    report_dir = Path(reports_dir or cfg.get("reports_dir", "reports"))
    report = _daily_report(report_dir, dry_run)
    metrics = report.get("backtest", {}).get("metrics", {})
    weekly = {
        "period": "weekly",
        "summary": {
            "signals": report["summary"]["signals"],
            "backtest_verdict": report["summary"]["backtest_verdict"],
            "health_ok": report["summary"]["health_ok"],
            "trade_count": metrics.get("trade_count", 0),
        },
        "member_performance": metrics.get("per_member", {}),
        "sector_performance": metrics.get("per_sector", {}),
        "latest_daily_report": report,
    }
    if not dry_run:
        write_json(report_dir / "weekly" / "latest.json", weekly)
    return weekly


def _daily_report(report_dir: Path, dry_run: bool) -> dict:
    if dry_run:
        return run_daily_report(dry_run=True)
    daily_path = report_dir / "daily" / "latest.json"
    existing = read_json_safe(daily_path, None, dict)
    if _valid_daily_report(existing):
        return existing
    return run_daily_report(dry_run=False, reports_dir=report_dir)


def _valid_daily_report(payload: object) -> bool:
    return (
        isinstance(payload, dict)
        and isinstance(payload.get("summary"), dict)
        and isinstance(payload.get("backtest"), dict)
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    print(json.dumps(to_jsonable(run(args.dry_run)), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
