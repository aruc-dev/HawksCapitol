from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Protocol

UTC = timezone.utc


@dataclass(frozen=True)
class RawFiling:
    source: str
    doc_id: str
    member_name: str
    filing_date: date
    url: str = ""
    payload: Any = None
    filing_type: str = "P"
    ingested_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class SourceHealth:
    source: str
    ok: bool
    newest_filing_date: date | None = None
    message: str = ""


class DisclosureSource(Protocol):
    name: str

    def fetch(self, since: date) -> list[RawFiling]: ...
    def parse(self, raw: RawFiling) -> list[dict]: ...
    def health(self) -> SourceHealth: ...


def parse_optional_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value).strip()[:10])
    except ValueError:
        return None


def first_parseable_date(row: dict[str, Any], *keys: str) -> date | None:
    for key in keys:
        parsed = parse_optional_date(row.get(key))
        if parsed is not None:
            return parsed
    return None
