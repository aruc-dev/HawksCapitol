from __future__ import annotations

import argparse
import json
import sys
from dataclasses import fields
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from analytics.member_score import compute_member_scores
from broker.paper_broker import PaperBroker
from core.models import Transaction, parse_date
from core.config_loader import load_config
from core.order_executor import execute_signal
from core.order_governor import OrderGovernor
from core.sample_data import sample_as_of, sample_sector_map, sample_transactions
from core.serialization import to_jsonable
from engine.copy_signal import build_copy_signals
from ingestion.storage import read_json, write_json


TRANSACTION_FIELDS = {field.name for field in fields(Transaction)}


def run(
    dry_run: bool = False,
    broker_state_path: str | Path | None = None,
    trade_log_path: str | Path | None = None,
    signals_path: str | Path | None = None,
    as_of: date | None = None,
) -> dict:
    cfg = load_config()
    data_dir = Path(cfg.get("data_dir", "data"))
    broker_state_path = Path(broker_state_path) if broker_state_path is not None else data_dir / "paper_broker" / "state.json"
    trade_log_path = Path(trade_log_path) if trade_log_path is not None else data_dir / "trade_log.json"
    signals_path = Path(signals_path) if signals_path is not None else data_dir / "signals" / "latest.json"
    txs, default_as_of, sector_map = _load_scan_inputs(cfg, dry_run)
    as_of = as_of or default_as_of
    scores = compute_member_scores(txs, as_of, sector_map=sector_map)
    signals = build_copy_signals(txs, scores, cfg, sector_map, as_of)
    accepted = []
    if not dry_run:
        broker = PaperBroker(broker_state_path)
        governor = OrderGovernor(cfg["risk"]["max_daily_orders"], cfg["risk"]["account_equity"] * cfg["risk"]["max_position_pct"])
        for sig in signals:
            if not sig.blocked_reason:
                accepted.append(execute_signal(sig, broker, cfg, price=100.0, governor=governor))
        write_json(signals_path, signals)
        write_json(trade_log_path, accepted)
    return {"signals": to_jsonable(signals), "accepted_orders": to_jsonable(accepted)}


def _load_scan_inputs(cfg: dict, dry_run: bool) -> tuple[list[Transaction], date, dict[str, str]]:
    if dry_run:
        return sample_transactions(), sample_as_of(), sample_sector_map()

    data_dir = Path(cfg.get("data_dir", "data"))
    tx_rows = read_json(data_dir / "canonical" / "transactions.json", [])
    sector_map = _load_sector_map(Path(cfg.get("sector_map_path", "config/sectors.json")))
    return _transactions_from_rows(tx_rows), date.today(), sector_map


def _load_sector_map(path: Path) -> dict[str, str]:
    rows = read_json(path, {})
    if not isinstance(rows, dict):
        raise ValueError(f"sector map must be a JSON object: {path}")
    return {str(symbol).upper(): str(sector) for symbol, sector in rows.items()}


def _transactions_from_rows(rows: object) -> list[Transaction]:
    if rows is None:
        return []
    if not isinstance(rows, list):
        raise ValueError("canonical transactions must be a list")
    return [_transaction_from_row(row) for row in rows]


def _transaction_from_row(row: object) -> Transaction:
    if not isinstance(row, dict):
        raise ValueError("canonical transaction rows must be objects")
    payload = {key: value for key, value in row.items() if key in TRANSACTION_FIELDS}
    payload["tx_date"] = _required_date(payload.get("tx_date"), "tx_date")
    payload["filing_date"] = _required_date(payload.get("filing_date"), "filing_date")
    return Transaction(**payload)


def _required_date(value: object, field_name: str) -> date:
    parsed = parse_date(value)  # type: ignore[arg-type]
    if parsed is None:
        raise ValueError(f"canonical transaction missing {field_name}")
    return parsed


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    print(json.dumps(run(args.dry_run), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
