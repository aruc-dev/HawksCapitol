from __future__ import annotations

from datetime import date
import os

from sources.base import RawFiling, SourceHealth, first_parseable_date
from sources.fmp import _normalize_row


CONGRESSINVESTS_ENDPOINT = "https://api.congressinvests.com/trades"


class CongressInvestsSource:
    name = "congressinvests"

    def __init__(self, api_key: str | None = None, fixture_payload: list[dict] | None = None, session=None, endpoint: str = CONGRESSINVESTS_ENDPOINT) -> None:
        self.api_key = api_key or os.getenv("CONGRESSINVESTS_API_KEY")
        self.fixture_payload = fixture_payload
        self.session = session
        self.endpoint = endpoint
        self._skipped_rows = 0
        self._last_health = SourceHealth(self.name, False, message="disabled until terms and free limits are verified")

    def fetch(self, since: date) -> list[RawFiling]:
        if self.fixture_payload is not None:
            filings = self._filings_from_rows(self.fixture_payload, since)
            self._last_health = SourceHealth(self.name, True, max((f.filing_date for f in filings), default=None), self._health_message("fixture", len(filings)))
            return filings
        if not self.api_key:
            self._last_health = SourceHealth(self.name, False, message="missing reviewed free API key; self-disabled")
            return []
        session = self.session or _requests_session()
        response = session.get(self.endpoint, headers={"Authorization": f"Bearer {self.api_key}"}, timeout=30)
        if response.status_code in {401, 402, 403, 429}:
            self._last_health = SourceHealth(self.name, False, message=f"entitlement/quota unavailable: HTTP {response.status_code}")
            return []
        if response.status_code != 200:
            self._last_health = SourceHealth(self.name, False, message=f"HTTP {response.status_code}")
            return []
        rows = response.json()
        filings = self._filings_from_rows(rows if isinstance(rows, list) else rows.get("data", []), since)
        self._last_health = SourceHealth(self.name, True, max((f.filing_date for f in filings), default=None), self._health_message("rows", len(filings)))
        return filings

    def parse(self, raw: RawFiling) -> list[dict]:
        rows = raw.payload if isinstance(raw.payload, list) else [raw.payload] if isinstance(raw.payload, dict) else []
        return [_normalize_row(raw, row) for row in rows]

    def health(self) -> SourceHealth:
        return self._last_health

    def _filings_from_rows(self, rows: list[dict], since: date) -> list[RawFiling]:
        filings = []
        self._skipped_rows = 0
        for idx, row in enumerate(rows):
            filing_date = first_parseable_date(row, "filing_date", "filingDate", "disclosureDate")
            if filing_date is None:
                self._skipped_rows += 1
                continue
            if filing_date < since:
                continue
            doc_id = str(row.get("doc_id") or row.get("documentId") or f"ci-{idx}")
            member = row.get("member_name") or row.get("representative") or row.get("senator") or "Unknown"
            filings.append(RawFiling(self.name, doc_id, member, filing_date, payload=row))
        return filings

    def _health_message(self, label: str, count: int) -> str:
        message = label if label == "fixture" else f"{count} {label}"
        if self._skipped_rows:
            message += f"; skipped {self._skipped_rows} invalid rows"
        return message


def _requests_session():
    import requests

    return requests.Session()
