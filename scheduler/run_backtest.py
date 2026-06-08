from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backtest.simulator import run_backtest
from core.config_loader import load_config
from core.sample_data import sample_as_of, sample_sector_map, sample_transactions
from ingestion.storage import write_json


def run(dry_run: bool = False, days: int = 365) -> dict:
    cfg = load_config()
    result = run_backtest(sample_transactions(), cfg, sample_sector_map(), sample_as_of())
    result["days"] = days
    if not dry_run:
        write_json("reports/backtest/latest.json", result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--days", type=int, default=365)
    args = parser.parse_args()
    print(json.dumps(run(args.dry_run, args.days), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
