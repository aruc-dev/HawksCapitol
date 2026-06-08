from __future__ import annotations

import argparse
import json
from datetime import date, timedelta
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.config_loader import load_config
from core.sample_data import SAMPLE_RECORDS
from core.serialization import to_jsonable
from core.source_registry import load_source_registry, validate_enabled_sources
from ingestion.normalizer import normalize_records
from ingestion.reconciler import reconcile_transactions
from ingestion.storage import write_json
from sources.congressinvests import CongressInvestsSource
from sources.finnhub import FinnhubSource
from sources.fmp import FMPSource
from sources.history_loader import load_house_archive_records, load_stock_watcher_records, validate_history_source
from sources.house_clerk import HouseClerkSource
from sources.senate_efd import SenateEFDSource


HOUSE_DRY_RUN_XML = """
<FinancialDisclosureReports>
  <Report>
    <DocID>HC-DRY-1</DocID>
    <FilingType>P</FilingType>
    <Name>Demo Representative</Name>
    <FilingDate>2026-06-01</FilingDate>
  </Report>
  <Report>
    <DocID>HC-DRY-2</DocID>
    <FilingType>A</FilingType>
    <Name>Ignored Annual</Name>
    <FilingDate>2026-06-01</FilingDate>
  </Report>
</FinancialDisclosureReports>
"""

HOUSE_DRY_RUN_PDFS = {
    "HC-DRY-1": b"""
Transaction Date | Asset | Ticker | Transaction Type | Amount | Owner
2026-05-01 | Apple Inc. | AAPL | Purchase | $1,001 - $15,000 | self
"""
}

SENATE_DRY_RUN_SEARCH = {
    "data": [
        {
            "doc_id": "SE-DRY-1",
            "member_name": "Demo Senator",
            "filing_date": "2026-06-02",
            "url": "/search/view/SE-DRY-1/",
        }
    ]
}

SENATE_DRY_RUN_REPORTS = {
    "SE-DRY-1": """
    <table>
      <tr><th>Transaction Date</th><th>Asset Name</th><th>Ticker</th><th>Transaction Type</th><th>Amount</th><th>Owner</th></tr>
      <tr><td>2026-05-05</td><td>NVIDIA Corporation</td><td>NVDA</td><td>Purchase</td><td>$50,001 - $100,000</td><td>Self</td></tr>
    </table>
    """
}

OPTIONAL_DRY_RUN_PAYLOAD = [
    {
        "doc_id": "API-DRY-1",
        "member_name": "Demo Senator",
        "filing_date": "2026-06-02",
        "transactionDate": "2026-05-05",
        "ticker": "NVDA",
        "assetDescription": "NVIDIA Corporation",
        "transactionType": "Purchase",
        "amountRange": "$50,001 - $100,000",
    }
]

STOCK_WATCHER_DRY_RUN_PAYLOAD = [
    {
        "doc_id": "SW-DRY-1",
        "member_name": "Demo Senator",
        "filing_date": "2024-06-01",
        "transaction_date": "2024-05-15",
        "ticker": "AAPL",
        "asset_description": "Apple Inc.",
        "type": "Purchase",
        "amount": "$1,001 - $15,000",
    }
]

HOUSE_ARCHIVE_DRY_RUN_XML = """
<FinancialDisclosureReports>
  <Report>
    <DocID>HA-2024-1</DocID>
    <FilingType>P</FilingType>
    <Name>Demo Representative</Name>
    <FilingDate>2024-06-01</FilingDate>
  </Report>
</FinancialDisclosureReports>
"""

HOUSE_ARCHIVE_DRY_RUN_PDFS = {
    "HA-2024-1": b"Transaction Date | Asset | Ticker | Transaction Type | Amount | Owner\n2024-05-15 | Microsoft Corp | MSFT | Purchase | $15,001 - $50,000 | self"
}


def run(
    dry_run: bool = False,
    source: str | None = None,
    since: date | None = None,
    year: int | None = None,
    output_dir: str | Path | None = None,
    reports_dir: str | Path | None = None,
) -> dict:
    cfg = load_config()
    registry = load_source_registry(cfg["source_registry_path"])
    validate_enabled_sources(cfg["sources"], registry)
    records, health = _load_records(source, dry_run, since, year)
    disclosures, txs = normalize_records(records)
    reconciled, warnings = reconcile_transactions(txs)
    payload = {"disclosures": disclosures, "transactions": reconciled, "warnings": warnings}
    data_dir = Path(output_dir or cfg.get("data_dir", "data"))
    report_dir = Path(reports_dir or cfg.get("reports_dir", "reports"))
    if not dry_run:
        write_json(data_dir / "canonical" / "disclosures.json", disclosures)
        write_json(data_dir / "canonical" / "transactions.json", reconciled)
        write_json(report_dir / "reconciliation.json", warnings)
    return {
        "source": source or "sample",
        "disclosures": len(disclosures),
        "transactions": len(reconciled),
        "warnings": len(warnings),
        "health": to_jsonable(health),
        "would_write": [
            str(data_dir / "canonical" / "disclosures.json"),
            str(data_dir / "canonical" / "transactions.json"),
            str(report_dir / "reconciliation.json"),
        ],
    }


def _load_records(source: str | None, dry_run: bool, since: date | None, year: int | None) -> tuple[list[dict], list[dict]]:
    if source is None or source == "sample":
        return SAMPLE_RECORDS, []
    if source == "enabled":
        cfg = load_config()
        records: list[dict] = []
        health: list[dict] = []
        for name, active in cfg["sources"].items():
            if not active:
                continue
            try:
                source_records, source_health = _load_records(name, dry_run, since, year)
                records.extend(source_records)
                health.extend(source_health)
            except Exception as exc:
                health.append({"source": name, "ok": False, "message": str(exc), "newest_filing_date": None})
        return records, health
    since = since or date.today() - timedelta(days=60)
    if source == "house_clerk":
        if dry_run:
            adapter = HouseClerkSource(fixture_xml=HOUSE_DRY_RUN_XML, fixture_pdfs=HOUSE_DRY_RUN_PDFS, year=year or 2026)
        else:
            adapter = HouseClerkSource(year=year)
        filings = adapter.fetch(since)
        records = []
        for filing in filings:
            records.extend(adapter.parse(filing))
        return records, [adapter.health().__dict__]
    if source == "senate_efd":
        if dry_run:
            adapter = SenateEFDSource(fixture_search_payload=SENATE_DRY_RUN_SEARCH, fixture_reports=SENATE_DRY_RUN_REPORTS)
        else:
            adapter = SenateEFDSource()
        filings = adapter.fetch(since)
        records = []
        for filing in filings:
            records.extend(adapter.parse(filing))
        return records, [adapter.health().__dict__]
    if source == "fmp":
        adapter = FMPSource(fixture_payload=OPTIONAL_DRY_RUN_PAYLOAD if dry_run else None)
        filings = adapter.fetch(since)
        records = []
        for filing in filings:
            records.extend(adapter.parse(filing))
        return records, [adapter.health().__dict__]
    if source == "congressinvests":
        adapter = CongressInvestsSource(fixture_payload=OPTIONAL_DRY_RUN_PAYLOAD if dry_run else None)
        filings = adapter.fetch(since)
        records = []
        for filing in filings:
            records.extend(adapter.parse(filing))
        return records, [adapter.health().__dict__]
    if source == "finnhub":
        adapter = FinnhubSource()
        return [], [adapter.health().__dict__]
    if source == "stock_watcher":
        registry = load_source_registry(load_config()["source_registry_path"])
        validate_history_source(registry["stock_watcher"], fixture_only=dry_run)
        result = load_stock_watcher_records(STOCK_WATCHER_DRY_RUN_PAYLOAD if dry_run else [], since, fixture_only=dry_run)
        return result.records, [row.__dict__ for row in result.health]
    if source == "house_archive":
        if not dry_run:
            raise ValueError("house_archive uses fixture data and is only available with dry_run=True")
        zip_bytes = _zip_bytes("2024FD.xml", HOUSE_ARCHIVE_DRY_RUN_XML)
        result = load_house_archive_records({year or 2024: zip_bytes}, HOUSE_ARCHIVE_DRY_RUN_PDFS, since)
        return result.records, [row.__dict__ for row in result.health]
    raise ValueError(f"unsupported ingest source: {source}")


def _zip_bytes(name: str, content: str) -> bytes:
    from io import BytesIO
    from zipfile import ZipFile

    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr(name, content)
    return buffer.getvalue()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--source",
        choices=["sample", "enabled", "house_clerk", "senate_efd", "fmp", "congressinvests", "finnhub", "stock_watcher", "house_archive"],
        default=None,
    )
    parser.add_argument("--since", help="YYYY-MM-DD filing-date lower bound")
    parser.add_argument("--year", type=int)
    args = parser.parse_args()
    since = date.fromisoformat(args.since) if args.since else None
    print(json.dumps(run(args.dry_run, args.source, since, args.year), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
