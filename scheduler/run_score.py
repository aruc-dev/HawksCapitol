from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from analytics.member_score import compute_member_scores
from analytics.sector_heatmap import compute_sector_heatmap
from core.config_loader import load_config
from core.sample_data import sample_as_of, sample_sector_map, sample_transactions
from core.serialization import to_jsonable
from ingestion.storage import write_json


def run(dry_run: bool = False) -> dict:
    load_config()
    txs = sample_transactions()
    as_of = sample_as_of()
    scores = compute_member_scores(txs, as_of)
    heat = compute_sector_heatmap(txs, sample_sector_map(), as_of)
    if not dry_run:
        write_json("data/canonical/member_scores/latest.json", scores)
        write_json("reports/sector_heatmap.json", heat)
    return {"member_scores": to_jsonable(scores), "sector_heatmap": heat}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    print(json.dumps(to_jsonable(run(args.dry_run)), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
