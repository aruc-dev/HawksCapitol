from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backtest.datasets import DEFAULT_BACKTEST_DATASET, infer_as_of, load_sector_map, load_transactions
from backtest.simulator import run_backtest
from core.config_loader import load_config
from core.sample_data import sample_as_of, sample_sector_map, sample_transactions
from ingestion.storage import write_json


def run(dry_run: bool = False, days: int = 365, dataset_path: str | Path | None = None, sample: bool = False) -> dict:
    cfg = load_config()
    if sample or (dry_run and dataset_path is None):
        transactions = sample_transactions()
        sector_map = sample_sector_map()
        as_of = sample_as_of()
        dataset = "sample"
    else:
        dataset_file = Path(dataset_path or cfg.get("backtest", {}).get("dataset_path", DEFAULT_BACKTEST_DATASET))
        transactions = load_transactions(dataset_file)
        sector_map = load_sector_map(cfg.get("sector_map_path", "config/sectors.json"))
        as_of = infer_as_of(transactions)
        dataset = str(dataset_file)
    result = run_backtest(transactions, cfg, sector_map, as_of, days=days)
    result["days"] = days
    result["dataset"] = dataset
    result["as_of"] = as_of.isoformat()
    result["input_transactions"] = len(transactions)
    if not dry_run:
        write_json(Path(cfg.get("reports_dir", "reports")) / "backtest" / "latest.json", result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--days", type=int, default=365)
    parser.add_argument("--dataset", help="Path to a checked-in backtest transaction dataset")
    parser.add_argument("--sample", action="store_true", help="Force the built-in sample dataset")
    args = parser.parse_args()
    print(json.dumps(run(args.dry_run, args.days, args.dataset, args.sample), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
