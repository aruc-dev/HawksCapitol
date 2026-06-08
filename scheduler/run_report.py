from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.config_loader import load_config
from core.serialization import to_jsonable
from ingestion.storage import read_json_safe, write_json
from scheduler.run_backtest import run as run_backtest_report
from scheduler.run_health_check import run as run_health
from scheduler.run_risk_check import run as run_risk
from scheduler.run_scan import run as run_scan_report


def run(dry_run: bool = False, reports_dir: str | Path | None = None) -> dict:
    cfg = load_config()
    report_dir = Path(reports_dir or cfg.get("reports_dir", "reports"))
    scan, backtest, health, risk = _report_inputs(cfg, report_dir, dry_run)
    report = {
        "summary": {
            "signals": len(scan["signals"]),
            "blocked_signals": sum(1 for sig in scan["signals"] if sig.get("blocked_reason")),
            "backtest_verdict": backtest.get("validation", {}).get("verdict", "not_available"),
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
        write_json(report_dir / "daily" / "latest.json", report)
    return report


def _report_inputs(cfg: dict, report_dir: Path, dry_run: bool) -> tuple[dict, dict, dict, dict]:
    if dry_run:
        return (
            run_scan_report(dry_run=True),
            run_backtest_report(dry_run=True),
            run_health(dry_run=True),
            run_risk(dry_run=True),
        )

    data_dir = Path(cfg.get("data_dir", "data"))
    scan = {
        "signals": _dict_rows(read_json_safe(data_dir / "signals" / "latest.json", [], list)),
        "accepted_orders": _dict_rows(read_json_safe(data_dir / "trade_log.json", [], list)),
    }
    backtest = read_json_safe(report_dir / "backtest" / "latest.json", _empty_backtest(), dict)
    health = run_health(dry_run=False)
    risk = {"decisions": _dict_rows(read_json_safe(report_dir / "risk_decisions.json", [], list))}
    return scan, backtest, health, risk


def _dict_rows(rows: list) -> list[dict]:
    return [row for row in rows if isinstance(row, dict)]


def _empty_backtest() -> dict:
    return {
        "metrics": {"trade_count": 0, "per_member": {}, "per_sector": {}},
        "validation": {"verdict": "not_available"},
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    print(json.dumps(to_jsonable(run(args.dry_run)), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
