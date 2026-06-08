from __future__ import annotations

import argparse
import json
from datetime import date
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.config_loader import load_config
from core.models import MarketSnapshot, Position
from core.sample_data import sample_as_of
from core.serialization import to_jsonable
from engine.sell_engine import evaluate_positions
from ingestion.storage import write_json


def _sample_positions() -> list[Position]:
    return [
        Position(
            trade_id="trade-demo-1",
            ticker="AAPL",
            asset_type="stock",
            entry_date=date(2026, 6, 1),
            entry_price=100.0,
            qty=10,
            stop_price=92.0,
            target_price=120.0,
            trail_high=118.0,
            copy_basis_tx_ids=["demo-1"],
            member_ids=["demo-senator"],
        )
    ]


def run(dry_run: bool = False) -> dict:
    cfg = load_config()
    market = MarketSnapshot(sample_as_of(), {"AAPL": 121.0})
    decisions = evaluate_positions(_sample_positions(), {"trade-demo-1": date(2026, 5, 15)}, market, cfg)
    if not dry_run:
        write_json("reports/risk_decisions.json", decisions)
    return {"decisions": to_jsonable(decisions)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    print(json.dumps(run(args.dry_run), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
