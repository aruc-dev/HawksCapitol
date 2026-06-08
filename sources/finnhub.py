from __future__ import annotations

from datetime import date

from sources.base import RawFiling, SourceHealth


class FinnhubSource:
    name = "finnhub"

    def fetch(self, since: date) -> list[RawFiling]:
        return []

    def parse(self, raw: RawFiling) -> list[dict]:
        return []

    def health(self) -> SourceHealth:
        return SourceHealth(self.name, False, message="premium endpoint; disabled by policy")
