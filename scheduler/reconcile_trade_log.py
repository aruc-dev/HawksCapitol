from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from broker.paper_broker import PaperBroker
from ingestion.storage import read_json


def run(
    dry_run: bool = False,
    broker_state_path: str | Path = "data/paper_broker/state.json",
    trade_log_path: str | Path = "data/trade_log.json",
) -> dict:
    trade_log = read_json(trade_log_path, [])
    return PaperBroker(broker_state_path).reconcile(trade_log)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    print(json.dumps(run(args.dry_run), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
