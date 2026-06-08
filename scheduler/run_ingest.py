from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.config_loader import load_config
from core.sample_data import SAMPLE_RECORDS
from core.source_registry import load_source_registry, validate_enabled_sources
from ingestion.normalizer import normalize_records
from ingestion.reconciler import reconcile_transactions
from ingestion.storage import write_json


def run(dry_run: bool = False) -> dict:
    cfg = load_config()
    registry = load_source_registry(cfg["source_registry_path"])
    validate_enabled_sources(cfg["sources"], registry)
    disclosures, txs = normalize_records(SAMPLE_RECORDS)
    reconciled, warnings = reconcile_transactions(txs)
    payload = {"disclosures": disclosures, "transactions": reconciled, "warnings": warnings}
    if not dry_run:
        write_json("data/canonical/disclosures.json", disclosures)
        write_json("data/canonical/transactions.json", reconciled)
        write_json("reports/reconciliation.json", warnings)
    return {"disclosures": len(disclosures), "transactions": len(reconciled), "warnings": len(warnings)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    print(json.dumps(run(args.dry_run), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
