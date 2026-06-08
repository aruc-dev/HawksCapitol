from __future__ import annotations

from datetime import date

from ingestion.normalizer import normalize_records


SAMPLE_RECORDS = [
    {
        "doc_id": "demo-1",
        "source": "house_clerk",
        "member_name": "Demo Senator",
        "member_id": "demo-senator",
        "filing_date": "2026-06-01",
        "tx_date": "2026-05-15",
        "ticker": "AAPL",
        "asset_name": "Apple Inc.",
        "tx_type": "Purchase",
        "amount": "$100,001 - $250,000",
        "owner": "self",
        "source_quality": "official",
        "parse_confidence": 0.98,
        "price_on_tx_date": 180.0,
        "price_on_filing_date": 190.0
    },
    {
        "doc_id": "demo-2",
        "source": "senate_efd",
        "member_name": "Demo Senator",
        "member_id": "demo-senator",
        "filing_date": "2026-06-02",
        "tx_date": "2026-05-20",
        "ticker": "MSFT",
        "asset_name": "Microsoft Corp",
        "tx_type": "Purchase",
        "amount": "$15,001 - $50,000",
        "owner": "spouse",
        "source_quality": "official",
        "parse_confidence": 0.95,
        "price_on_tx_date": 420.0,
        "price_on_filing_date": 425.0
    },
    {
        "doc_id": "demo-3",
        "source": "house_clerk",
        "member_name": "Demo Senator",
        "member_id": "demo-senator",
        "filing_date": "2026-06-03",
        "tx_date": "2026-05-25",
        "ticker": "NVDA",
        "asset_name": "NVIDIA Corporation",
        "tx_type": "Purchase",
        "amount": "$50,001 - $100,000",
        "owner": "self",
        "source_quality": "official",
        "parse_confidence": 0.97,
        "price_on_tx_date": 120.0,
        "price_on_filing_date": 126.0
    }
]


def sample_transactions():
    return normalize_records(SAMPLE_RECORDS)[1]


def sample_as_of() -> date:
    return date(2026, 6, 7)


def sample_sector_map() -> dict[str, str]:
    return {"AAPL": "Technology", "MSFT": "Technology", "NVDA": "Technology", "SPY": "Benchmark"}
