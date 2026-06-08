from __future__ import annotations

from datetime import date
from html.parser import HTMLParser

from sources.base import RawFiling, SourceHealth


class _TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.in_cell = False
        self.current: list[str] = []
        self.rows: list[list[str]] = []
        self.row: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in {"td", "th"}:
            self.in_cell = True
            self.current = []
        if tag == "tr":
            self.row = []

    def handle_data(self, data: str) -> None:
        if self.in_cell:
            self.current.append(data.strip())

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"}:
            self.in_cell = False
            self.row.append(" ".join(part for part in self.current if part))
        if tag == "tr" and self.row:
            self.rows.append(self.row)


def parse_senate_ptr_html(html: str) -> list[dict]:
    parser = _TableParser()
    parser.feed(html)
    if not parser.rows:
        return []
    header = [h.lower().replace(" ", "_") for h in parser.rows[0]]
    records = []
    for row in parser.rows[1:]:
        padded = row + [""] * max(0, len(header) - len(row))
        records.append(dict(zip(header, padded)))
    return records


class SenateEFDSource:
    name = "senate_efd"

    def __init__(self, fixture_rows: list[RawFiling] | None = None) -> None:
        self.fixture_rows = fixture_rows or []

    def fetch(self, since: date) -> list[RawFiling]:
        return [row for row in self.fixture_rows if row.filing_date >= since]

    def parse(self, raw: RawFiling) -> list[dict]:
        if isinstance(raw.payload, str):
            rows = parse_senate_ptr_html(raw.payload)
            for row in rows:
                row.setdefault("doc_id", raw.doc_id)
                row.setdefault("source", raw.source)
                row.setdefault("member_name", raw.member_name)
                row.setdefault("filing_date", raw.filing_date.isoformat())
            return rows
        return raw.payload if isinstance(raw.payload, list) else []

    def health(self) -> SourceHealth:
        newest = max((row.filing_date for row in self.fixture_rows), default=None)
        return SourceHealth(self.name, True, newest, "fixture")
