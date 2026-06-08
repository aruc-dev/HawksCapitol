from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from broker.paper_broker import PaperBroker
from core.config_loader import load_config
from core.models import parse_date
from core.sample_data import sample_transactions
from core.serialization import to_jsonable
from core.source_registry import load_source_registry, validate_enabled_sources
from ingestion.storage import read_json_safe, write_json


def run(dry_run: bool = False, as_of: date | None = None) -> dict:
    as_of = as_of or date.today()
    cfg = load_config()
    registry = load_source_registry(cfg["source_registry_path"])
    validate_enabled_sources(cfg["sources"], registry)
    transactions = _load_transactions(dry_run, cfg)
    source_status = _source_status(cfg, registry, transactions, as_of)
    alerts = _alerts(source_status, cfg)
    broker = PaperBroker(Path(cfg.get("data_dir", "data")) / "paper_broker" / "state.json")
    payload = {
        "ok": not any(alert["severity"] == "error" for alert in alerts),
        "enabled_sources": sorted(name for name, active in cfg["sources"].items() if active),
        "mode": cfg["mode"],
        "source_status": source_status,
        "alerts": alerts,
        "broker": {"positions": to_jsonable(broker.positions())},
    }
    if not dry_run and alerts:
        write_json(Path(cfg.get("reports_dir", "reports")) / "alerts" / "health.json", payload)
    return payload


def _load_transactions(dry_run: bool, cfg: dict) -> list[dict]:
    if dry_run:
        return [tx.__dict__ for tx in sample_transactions()]
    rows = read_json_safe(Path(cfg.get("data_dir", "data")) / "canonical" / "transactions.json", [], list)
    return [row for row in rows if isinstance(row, dict)]


def _source_status(cfg: dict, registry: dict, transactions: list[dict], as_of: date) -> dict:
    status = {}
    for name, entry in registry.items():
        rows = [tx for tx in transactions if tx.get("source") == name]
        newest = max((parsed for tx in rows if (parsed := parse_date(tx.get("filing_date"))) is not None), default=None)
        stale_days = (as_of - newest).days if newest else None
        status[name] = {
            "enabled": bool(cfg["sources"].get(name, False)),
            "production_status": entry.production_status,
            "cost": entry.cost,
            "automated_access_allowed": entry.automated_access_allowed,
            "newest_filing_date": newest.isoformat() if newest else None,
            "stale_days": stale_days,
            "row_count": len(rows),
        }
    return status


def _alerts(source_status: dict, cfg: dict) -> list[dict]:
    alerts = []
    max_stale = cfg.get("health", {}).get("max_source_staleness_days", 7)
    for source, status in source_status.items():
        if not status["enabled"]:
            continue
        if status["newest_filing_date"] is None:
            alerts.append({"severity": "warning", "source": source, "reason": "no_recent_filings"})
        elif status["stale_days"] > max_stale:
            alerts.append(
                {
                    "severity": "warning",
                    "source": source,
                    "reason": "source_stale",
                    "stale_days": status["stale_days"],
                }
            )
    return alerts


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    print(json.dumps(to_jsonable(run(args.dry_run)), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
