from __future__ import annotations

from datetime import date, datetime
from html.parser import HTMLParser
import re
import time
from urllib.parse import urljoin

from ingestion.pdf_parser import extract_text_from_pdf_bytes
from sources.base import RawFiling, SourceHealth
from sources.house_clerk import parse_house_ptr_text


SENATE_SEARCH_URL = "https://efdsearch.senate.gov/search/"
SENATE_REPORT_DATA_URL = "https://efdsearch.senate.gov/search/report/data/"
DEFAULT_USER_AGENT = "HawksCapitol/0.1 paper research contact=local"


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
    records: list[dict] = []
    for table in _tables_from_rows(parser.rows):
        if not table:
            continue
        header = [_normalize_header(h) for h in table[0]]
        for row in table[1:]:
            padded = row + [""] * max(0, len(header) - len(row))
            raw = dict(zip(header, padded))
            normalized = normalize_senate_transaction_row(raw)
            if normalized:
                records.append(normalized)
    return records


def normalize_senate_transaction_row(row: dict) -> dict:
    amount = _pick(row, "amount", "transaction_amount", "value")
    tx_date = _pick(row, "transaction_date", "date")
    tx_type = _pick(row, "type", "transaction_type")
    asset_name = _pick(row, "asset_name", "asset", "description", "security")
    ticker = _pick(row, "ticker", "symbol")
    owner = _pick(row, "owner")
    if not (amount and tx_date and tx_type and (asset_name or ticker)):
        return {}
    return {
        "tx_date": tx_date,
        "ticker": ticker or None,
        "asset_name": asset_name or ticker,
        "tx_type": tx_type,
        "amount": amount,
        "owner": owner or "self",
    }


def parse_senate_search_rows(payload: dict | list, since: date) -> list[RawFiling]:
    rows = payload.get("data", payload.get("rows", [])) if isinstance(payload, dict) else payload
    filings: list[RawFiling] = []
    for idx, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        filing_date = _parse_date(_pick(row, "filing_date", "date_received", "filed_date", "filingdate"))
        if filing_date is None or filing_date < since:
            continue
        doc_id = str(_pick(row, "doc_id", "report_id", "document_id") or f"senate-{idx}")
        member_name = _pick(row, "member_name", "name", "filer_name") or "Unknown"
        url = _pick(row, "url", "report_url", "link")
        filings.append(RawFiling("senate_efd", doc_id, member_name, filing_date, url=url, payload=row))
    return filings


class SenateEFDSource:
    name = "senate_efd"

    def __init__(
        self,
        fixture_rows: list[RawFiling] | None = None,
        fixture_search_payload: dict | list | None = None,
        fixture_reports: dict[str, str | bytes | list[dict]] | None = None,
        session=None,
        timeout: int = 30,
        max_retries: int = 3,
        backoff_seconds: float = 1.0,
    ) -> None:
        self.fixture_rows = fixture_rows or []
        self.fixture_search_payload = fixture_search_payload
        self.fixture_reports = fixture_reports or {}
        self.session = session
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff_seconds = backoff_seconds
        self._last_health = SourceHealth(self.name, False, message="not checked")

    def fetch(self, since: date) -> list[RawFiling]:
        try:
            if self.fixture_rows:
                filings = [row for row in self.fixture_rows if row.filing_date >= since]
            elif self.fixture_search_payload is not None:
                filings = parse_senate_search_rows(self.fixture_search_payload, since)
            else:
                filings = self._search(since)
            newest = max((row.filing_date for row in filings), default=None)
            self._last_health = SourceHealth(self.name, True, newest, f"{len(filings)} filings since {since}")
            return filings
        except Exception as exc:
            self._last_health = SourceHealth(self.name, False, message=str(exc))
            raise

    def parse(self, raw: RawFiling) -> list[dict]:
        payload = self.fixture_reports.get(raw.doc_id, raw.payload)
        if isinstance(payload, list):
            rows = payload
        elif isinstance(payload, bytes):
            text, confidence = extract_text_from_pdf_bytes(payload)
            rows = parse_house_ptr_text(text, raw, confidence)
        elif isinstance(payload, str):
            rows = parse_senate_ptr_html(payload)
        elif isinstance(payload, dict) and payload.get("transactions"):
            rows = payload["transactions"]
        elif isinstance(payload, dict) and payload.get("html"):
            rows = parse_senate_ptr_html(payload["html"])
        elif isinstance(payload, dict) and payload.get("pdf_bytes"):
            text, confidence = extract_text_from_pdf_bytes(payload["pdf_bytes"])
            rows = parse_house_ptr_text(text, raw, confidence)
        else:
            report = self._fetch_report(raw)
            rows = self.parse(RawFiling(raw.source, raw.doc_id, raw.member_name, raw.filing_date, raw.url, report))
        return [self._with_raw_context(raw, row) for row in rows if row]

    def health(self) -> SourceHealth:
        return self._last_health

    def _search(self, since: date) -> list[RawFiling]:
        session = self.session or _requests_session()
        landing = self._request(session, "get", SENATE_SEARCH_URL)
        csrf = _extract_csrf_token(landing.text)
        headers = {"User-Agent": DEFAULT_USER_AGENT, "Referer": SENATE_SEARCH_URL}
        if csrf:
            headers["X-CSRFToken"] = csrf
        payload = {
            "start": 0,
            "length": 100,
            "report_types": ["Periodic Transaction Report"],
            "submitted_start_date": since.strftime("%m/%d/%Y"),
        }
        response = self._request(session, "post", SENATE_REPORT_DATA_URL, data=payload, headers=headers)
        return parse_senate_search_rows(response.json(), since)

    def _fetch_report(self, raw: RawFiling) -> str | bytes | list[dict]:
        if not raw.url:
            return []
        session = self.session or _requests_session()
        url = urljoin(SENATE_SEARCH_URL, raw.url)
        response = self._request(session, "get", url)
        content_type = response.headers.get("Content-Type", "").lower()
        if "pdf" in content_type or raw.url.lower().endswith(".pdf"):
            return response.content
        return response.text

    def _request(self, session, method: str, url: str, **kwargs):
        headers = kwargs.pop("headers", {})
        headers.setdefault("User-Agent", DEFAULT_USER_AGENT)
        last_error = None
        for attempt in range(self.max_retries):
            try:
                request = getattr(session, method)
                response = request(url, headers=headers, timeout=self.timeout, **kwargs)
                if response.status_code in {200, 201}:
                    return response
                last_error = RuntimeError(f"{method.upper()} {url} returned HTTP {response.status_code}")
            except Exception as exc:
                last_error = exc
            if attempt + 1 < self.max_retries:
                time.sleep(self.backoff_seconds * (attempt + 1))
        raise RuntimeError(f"failed Senate eFD request {url}: {last_error}")

    def _with_raw_context(self, raw: RawFiling, row: dict) -> dict:
        normalized = normalize_senate_transaction_row(row) or row
        return {
            "doc_id": raw.doc_id,
            "source": raw.source,
            "member_name": raw.member_name,
            "filing_date": raw.filing_date.isoformat(),
            "url": raw.url,
            "source_quality": "official",
            "parse_confidence": row.get("parse_confidence", 0.9),
            "amends_doc_id": row.get("amends_doc_id") or row.get("amended_doc_id") or row.get("amends"),
            **normalized,
        }


def _requests_session():
    import requests

    return requests.Session()


def _tables_from_rows(rows: list[list[str]]) -> list[list[list[str]]]:
    if not rows:
        return []
    tables: list[list[list[str]]] = []
    current: list[list[str]] = []
    for row in rows:
        if _looks_like_header(row) and current:
            tables.append(current)
            current = [row]
        else:
            current.append(row)
    if current:
        tables.append(current)
    return tables


def _looks_like_header(row: list[str]) -> bool:
    text = " ".join(cell.lower() for cell in row)
    return "transaction" in text and ("amount" in text or "ticker" in text or "asset" in text)


def _normalize_header(value: str) -> str:
    text = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    aliases = {
        "transaction": "transaction_type",
        "transaction_type": "transaction_type",
        "transaction_date": "transaction_date",
        "date": "transaction_date",
        "asset": "asset_name",
        "asset_name": "asset_name",
        "security": "asset_name",
        "amount": "amount",
        "owner": "owner",
        "ticker": "ticker",
        "symbol": "ticker",
    }
    return aliases.get(text, text)


def _pick(row: dict, *keys: str) -> str:
    for key in keys:
        value = row.get(key)
        if value:
            return str(value).strip()
    return ""


def _parse_date(value: str) -> date | None:
    if not value:
        return None
    text = value.strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(text[:10], fmt).date()
        except ValueError:
            continue
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _extract_csrf_token(html: str) -> str:
    match = re.search(r"name=[\"']csrfmiddlewaretoken[\"'][^>]*value=[\"']([^\"']+)", html)
    if match:
        return match.group(1)
    match = re.search(r"value=[\"']([^\"']+)[\"'][^>]*name=[\"']csrfmiddlewaretoken[\"']", html)
    return match.group(1) if match else ""
