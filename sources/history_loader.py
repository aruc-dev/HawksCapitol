from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from core.source_registry import ALLOWED_COSTS, SourceRegistryEntry
from sources.base import RawFiling, SourceHealth
from sources.house_clerk import HouseClerkSource
from sources.stock_watcher import StockWatcherSource


class HistorySourceBlocked(ValueError):
    pass


@dataclass(frozen=True)
class HistoricalLoadResult:
    records: list[dict]
    health: list[SourceHealth]


def validate_history_source(entry: SourceRegistryEntry, fixture_only: bool = False) -> None:
    if fixture_only:
        return
    if entry.cost not in ALLOWED_COSTS:
        raise HistorySourceBlocked(f"{entry.name} has blocked cost status {entry.cost}")
    if not entry.terms_reviewed_at:
        raise HistorySourceBlocked(f"{entry.name} is missing terms review for historical reuse")
    if not entry.automated_access_allowed:
        raise HistorySourceBlocked(f"{entry.name} automated historical access is not approved")
    if entry.production_status not in {"history_only", "enabled"}:
        raise HistorySourceBlocked(f"{entry.name} is not approved for historical loading")


def load_stock_watcher_records(records: list[dict], since: date, fixture_only: bool = True) -> HistoricalLoadResult:
    source = StockWatcherSource(records=records, fixture_only=fixture_only)
    filings = source.fetch(since)
    parsed = [row for filing in filings for row in source.parse(filing)]
    return HistoricalLoadResult(parsed, [source.health()])


def load_house_archive_records(
    year_zips: dict[int, bytes],
    fixture_pdfs: dict[str, bytes],
    since: date,
) -> HistoricalLoadResult:
    records: list[dict] = []
    health: list[SourceHealth] = []
    for year, zip_bytes in sorted(year_zips.items()):
        source = HouseClerkSource(fixture_zip=zip_bytes, fixture_pdfs=fixture_pdfs, year=year)
        filings = source.fetch(since)
        for filing in filings:
            records.extend(source.parse(filing))
        health.append(source.health())
    return HistoricalLoadResult(records, health)
