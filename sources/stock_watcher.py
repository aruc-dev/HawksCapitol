from __future__ import annotations

from datetime import date

from sources.base import RawFiling, SourceHealth, first_parseable_date


class StockWatcherSource:
    name = "stock_watcher"

    def __init__(self, records: list[dict] | None = None, fixture_only: bool = True) -> None:
        self.records = records or []
        self.fixture_only = fixture_only
        self._last_health = SourceHealth(self.name, bool(self.records), message="history_only fixture" if fixture_only else "history_only")

    def fetch(self, since: date) -> list[RawFiling]:
        filings = []
        skipped = 0
        for idx, record in enumerate(self.records):
            filing_date = first_parseable_date(record, "filing_date", "disclosure_date", "disclosureDate")
            if filing_date is None:
                skipped += 1
                continue
            if filing_date >= since:
                doc_id = str(record.get("doc_id") or record.get("document_id") or f"sw-{idx}")
                member = record.get("member_name") or record.get("senator") or record.get("representative") or "Unknown"
                filings.append(RawFiling(self.name, doc_id, member, filing_date, payload=[record]))
        newest = max((filing.filing_date for filing in filings), default=None)
        message = f"{len(filings)} history rows"
        if skipped:
            message += f"; skipped {skipped} invalid rows"
        self._last_health = SourceHealth(self.name, bool(self.records), newest, message)
        return filings

    def parse(self, raw: RawFiling) -> list[dict]:
        rows = raw.payload if isinstance(raw.payload, list) else []
        return [_normalize_row(raw, row) for row in rows]

    def health(self) -> SourceHealth:
        return self._last_health


def _normalize_row(raw: RawFiling, row: dict) -> dict:
    return {
        "doc_id": raw.doc_id,
        "source": raw.source,
        "member_name": raw.member_name,
        "filing_date": raw.filing_date.isoformat(),
        "tx_date": row.get("tx_date") or row.get("transaction_date") or row.get("transactionDate"),
        "ticker": row.get("ticker") or row.get("symbol"),
        "asset_name": row.get("asset_name") or row.get("asset_description") or row.get("assetDescription") or row.get("ticker"),
        "tx_type": row.get("tx_type") or row.get("type") or row.get("transaction_type") or row.get("transactionType"),
        "amount": row.get("amount") or row.get("amount_range") or row.get("amountRange"),
        "owner": row.get("owner") or "self",
        "source_quality": "third_party_only",
        "parse_confidence": float(row.get("parse_confidence", 0.8)),
    }
