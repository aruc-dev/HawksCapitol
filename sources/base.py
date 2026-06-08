from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any, Protocol


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
