from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.serialization import to_jsonable
from ingestion.storage import write_json
from scheduler.run_backtest import run as run_backtest_report
from scheduler.run_health_check import run as run_health
from scheduler.run_risk_check import run as run_risk
from scheduler.run_scan import run as run_scan_report


def run(dry_run: bool = False) -> dict:
    scan = run_scan_report(dry_run=True)
    backtest = run_backtest_report(dry_run=True)
    health = run_health(dry_run=True)
    risk = run_risk(dry_run=True)
    report = {
        "summary": {
            "signals": len(scan["signals"]),
            "blocked_signals": sum(1 for sig in scan["signals"] if sig.get("blocked_reason")),
            "backtest_verdict": backtest["validation"]["verdict"],
            "health_ok": health["ok"],
            "alerts": len(health["alerts"]),
            "risk_decisions": len(risk["decisions"]),
        },
        "scan": scan,
        "backtest": backtest,
        "health": health,
        "risk": risk,
    }
    if not dry_run:
        write_json("reports/daily/latest.json", report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    print(json.dumps(to_jsonable(run(args.dry_run)), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
