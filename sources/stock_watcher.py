from __future__ import annotations

from datetime import date

from sources.base import RawFiling, SourceHealth


class StockWatcherSource:
    name = "stock_watcher"

    def __init__(self, records: list[dict] | None = None) -> None:
        self.records = records or []

    def fetch(self, since: date) -> list[RawFiling]:
        filings = []
        for idx, record in enumerate(self.records):
            filing_date = date.fromisoformat(record["filing_date"])
            if filing_date >= since:
                filings.append(RawFiling(self.name, f"sw-{idx}", record["member_name"], filing_date, payload=[record]))
        return filings

    def parse(self, raw: RawFiling) -> list[dict]:
        return raw.payload if isinstance(raw.payload, list) else []

    def health(self) -> SourceHealth:
        return SourceHealth(self.name, bool(self.records), message="history_only")
