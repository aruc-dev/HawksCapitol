from __future__ import annotations

from datetime import date

from sources.base import RawFiling, SourceHealth


class CongressInvestsSource:
    name = "congressinvests"

    def fetch(self, since: date) -> list[RawFiling]:
        return []

    def parse(self, raw: RawFiling) -> list[dict]:
        return raw.payload if isinstance(raw.payload, list) else []

    def health(self) -> SourceHealth:
        return SourceHealth(self.name, False, message="disabled until terms and free limits are verified")
