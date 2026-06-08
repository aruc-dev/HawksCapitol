from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scheduler.run_backtest import run as run_backtest_report
from scheduler.run_health_check import run as run_health
from scheduler.run_scan import run as run_scan_report
from ingestion.storage import write_json


def run(dry_run: bool = False) -> dict:
    report = {
        "scan": run_scan_report(dry_run=True),
        "backtest": run_backtest_report(dry_run=True),
        "health": run_health(dry_run=True),
    }
    if not dry_run:
        write_json("reports/daily/latest.json", report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    print(json.dumps(run(args.dry_run), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
