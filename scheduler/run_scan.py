from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from analytics.member_score import compute_member_scores
from broker.paper_broker import PaperBroker
from core.config_loader import load_config
from core.order_executor import execute_signal
from core.order_governor import OrderGovernor
from core.sample_data import sample_as_of, sample_sector_map, sample_transactions
from core.serialization import to_jsonable
from engine.copy_signal import build_copy_signals
from ingestion.storage import write_json


def run(
    dry_run: bool = False,
    broker_state_path: str | Path = "data/paper_broker/state.json",
    trade_log_path: str | Path = "data/trade_log.json",
    signals_path: str | Path = "data/signals/latest.json",
) -> dict:
    cfg = load_config()
    txs = sample_transactions()
    as_of = sample_as_of()
    scores = compute_member_scores(txs, as_of)
    signals = build_copy_signals(txs, scores, cfg, sample_sector_map(), as_of)
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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    print(json.dumps(run(args.dry_run), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
