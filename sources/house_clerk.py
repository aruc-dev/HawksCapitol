from __future__ import annotations

from datetime import date
import json
from pathlib import Path
import re
import time
from xml.etree import ElementTree
from zipfile import ZipFile
from io import BytesIO

from ingestion.pdf_parser import extract_text_from_pdf_bytes
from sources.base import RawFiling, SourceHealth, parse_optional_date


HOUSE_INDEX_URL = "https://disclosures-clerk.house.gov/public_disc/financial-pdfs/{year}FD.zip"
HOUSE_PTR_URL = "https://disclosures-clerk.house.gov/public_disc/ptr-pdfs/{year}/{doc_id}.pdf"
DEFAULT_USER_AGENT = "HawksCapitol/0.1 paper research contact=local"


def parse_house_index(xml_text: str, year: int) -> list[RawFiling]:
    root = ElementTree.fromstring(xml_text)
    filings: list[RawFiling] = []
    for node in root.iter():
        children = {_local_name(child.tag).lower(): (child.text or "").strip() for child in list(node)}
        filing_type = children.get("filingtype") or children.get("filing_type")
        doc_id = children.get("docid") or children.get("doc_id")
        if not doc_id or filing_type != "P":
            continue
        name = _house_member_name(children)
        filing_date = _parse_house_date(children.get("filingdate") or children.get("filing_date"), year)
        if filing_date is None:
            continue
        filings.append(
            RawFiling(
                source="house_clerk",
                doc_id=doc_id,
                member_name=name,
                filing_date=filing_date,
                url=HOUSE_PTR_URL.format(year=year, doc_id=doc_id),
                payload={**children, "year": year},
                filing_type=filing_type,
            )
        )
    return filings


def parse_house_index_zip(zip_bytes: bytes, year: int) -> list[RawFiling]:
    with ZipFile(BytesIO(zip_bytes)) as archive:
        names = archive.namelist()
        preferred = f"{year}FD.xml"
        xml_name = preferred if preferred in names else next((name for name in names if name.lower().endswith(".xml")), "")
        if not xml_name:
            raise ValueError("House Clerk ZIP does not contain an XML index")
        xml_text = archive.read(xml_name).decode("utf-8-sig")
    return parse_house_index(xml_text, year)


def parse_house_ptr_text(text: str, raw: RawFiling, confidence: float = 0.8) -> list[dict]:
    records: list[dict] = []
    lines = _logical_lines(text)
    for line in lines:
        if _is_header_line(line):
            continue
        parsed = _parse_delimited_row(line)
        if not parsed:
            continue
        records.append(
            {
                "doc_id": raw.doc_id,
                "source": raw.source,
                "member_name": raw.member_name,
                "filing_date": raw.filing_date.isoformat(),
                "url": raw.url,
                "source_quality": "official",
                "parse_confidence": confidence,
                "raw_ref": line,
                **parsed,
            }
        )
    if records:
        return records
    for parsed in _parse_house_table_blocks(lines):
        records.append(
            {
                "doc_id": raw.doc_id,
                "source": raw.source,
                "member_name": raw.member_name,
                "filing_date": raw.filing_date.isoformat(),
                "url": raw.url,
                "source_quality": "official",
                "parse_confidence": confidence,
                "raw_ref": parsed.pop("raw_ref", ""),
                **parsed,
            }
        )
    if records:
        return records
    for line in lines:
        if _is_header_line(line):
            continue
        parsed = _parse_freeform_row(line)
        if not parsed:
            continue
        records.append(
            {
                "doc_id": raw.doc_id,
                "source": raw.source,
                "member_name": raw.member_name,
                "filing_date": raw.filing_date.isoformat(),
                "url": raw.url,
                "source_quality": "official",
                "parse_confidence": confidence,
                "raw_ref": line,
                **parsed,
            }
        )
    return records


class HouseClerkSource:
    name = "house_clerk"

    def __init__(
        self,
        fixture_xml: str | None = None,
        fixture_zip: bytes | None = None,
        fixture_pdfs: dict[str, bytes] | None = None,
        year: int | None = None,
        cache_dir: str | Path = "data/raw/house_clerk",
        session=None,
        timeout: int = 30,
        max_retries: int = 3,
        backoff_seconds: float = 1.0,
    ) -> None:
        self.fixture_xml = fixture_xml
        self.fixture_zip = fixture_zip
        self.fixture_pdfs = fixture_pdfs or {}
        self.year = year or date.today().year
        self.cache_dir = Path(cache_dir)
        self.session = session
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff_seconds = backoff_seconds
        self._last_health = SourceHealth(self.name, False, message="not checked")

    def fetch(self, since: date) -> list[RawFiling]:
        try:
            if self.fixture_xml:
                filings = parse_house_index(self.fixture_xml, self.year)
            elif self.fixture_zip:
                filings = parse_house_index_zip(self.fixture_zip, self.year)
            else:
                zip_bytes = self._download_index_zip()
                filings = parse_house_index_zip(zip_bytes, self.year)
            filtered = [filing for filing in filings if filing.filing_date >= since]
            newest = max((filing.filing_date for filing in filings), default=None)
            self._last_health = SourceHealth(self.name, True, newest, f"{len(filtered)} filings since {since}")
            return filtered
        except Exception as exc:
            self._last_health = SourceHealth(self.name, False, message=str(exc))
            raise

    def parse(self, raw: RawFiling) -> list[dict]:
        payload = raw.payload if isinstance(raw.payload, dict) else {}
        if payload.get("transactions"):
            return [self._with_raw_context(raw, row, 1.0) for row in payload["transactions"]]
        pdf_bytes = payload.get("pdf_bytes") or self.fixture_pdfs.get(raw.doc_id)
        if pdf_bytes is None:
            pdf_bytes = self.fetch_ptr_pdf(raw.doc_id, int(payload.get("year") or raw.filing_date.year))
        text, confidence = extract_text_from_pdf_bytes(pdf_bytes)
        rows = parse_house_ptr_text(text, raw, confidence)
        if rows:
            return rows
        fallback = _parse_index_payload(payload)
        return [self._with_raw_context(raw, fallback, min(confidence, 0.5))] if fallback else []

    def health(self) -> SourceHealth:
        return self._last_health

    def fetch_ptr_pdf(self, doc_id: str, year: int | None = None) -> bytes:
        if doc_id in self.fixture_pdfs:
            return self.fixture_pdfs[doc_id]
        year = year or self.year
        cache_path = self.cache_dir / "ptr-pdfs" / str(year) / f"{doc_id}.pdf"
        url = HOUSE_PTR_URL.format(year=year, doc_id=doc_id)
        return self._download_with_cache(url, cache_path)

    def _download_index_zip(self) -> bytes:
        cache_path = self.cache_dir / "financial-pdfs" / f"{self.year}FD.zip"
        url = HOUSE_INDEX_URL.format(year=self.year)
        return self._download_with_cache(url, cache_path)

    def _download_with_cache(self, url: str, cache_path: Path) -> bytes:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        meta_path = cache_path.with_suffix(cache_path.suffix + ".meta.json")
        headers = {"User-Agent": DEFAULT_USER_AGENT}
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                meta = {}
            if meta.get("etag"):
                headers["If-None-Match"] = meta["etag"]
            if meta.get("last_modified"):
                headers["If-Modified-Since"] = meta["last_modified"]
        session = self.session or _requests_session()
        last_error = None
        for attempt in range(self.max_retries):
            try:
                response = session.get(url, headers=headers, timeout=self.timeout)
                if response.status_code == 304 and cache_path.exists():
                    return cache_path.read_bytes()
                if response.status_code == 200:
                    content = response.content
                    cache_path.write_bytes(content)
                    meta = {
                        "url": url,
                        "etag": response.headers.get("ETag"),
                        "last_modified": response.headers.get("Last-Modified"),
                    }
                    meta_path.write_text(json.dumps(meta, indent=2, sort_keys=True), encoding="utf-8")
                    return content
                last_error = RuntimeError(f"GET {url} returned HTTP {response.status_code}")
            except Exception as exc:
                last_error = exc
            if attempt + 1 < self.max_retries:
                time.sleep(self.backoff_seconds * (attempt + 1))
        if cache_path.exists():
            return cache_path.read_bytes()
        raise RuntimeError(f"failed to fetch House Clerk URL {url}: {last_error}")

    def _with_raw_context(self, raw: RawFiling, row: dict, confidence: float) -> dict:
        return {
            "doc_id": raw.doc_id,
            "source": raw.source,
            "member_name": raw.member_name,
            "filing_date": raw.filing_date.isoformat(),
            "url": raw.url,
            "source_quality": "official",
            "parse_confidence": row.get("parse_confidence", confidence),
            **row,
        }


def _requests_session():
    import requests

    return requests.Session()


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _parse_house_date(value: str | None, year: int) -> date | None:
    if not value:
        return date(year, 1, 1)
    text = value.strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
        try:
            from datetime import datetime

            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return parse_optional_date(text)


def _house_member_name(children: dict[str, str]) -> str:
    if children.get("name"):
        return children["name"]
    parts = [children.get("first", ""), children.get("last", ""), children.get("suffix", "")]
    name = " ".join(part.strip() for part in parts if part.strip())
    return name or "Unknown"


def _logical_lines(text: str) -> list[str]:
    lines = []
    for line in text.splitlines():
        line = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", "", line)
        clean = re.sub(r"\s+", " ", line).strip()
        if clean:
            lines.append(clean)
    return lines


def _is_header_line(line: str) -> bool:
    text = line.lower()
    return "transaction" in text and "amount" in text and ("asset" in text or "ticker" in text)


def _parse_delimited_row(line: str) -> dict | None:
    delimiter = "|" if "|" in line else "\t" if "\t" in line else None
    if not delimiter:
        return None
    parts = [part.strip() for part in line.split(delimiter)]
    if len(parts) < 5:
        return None
    if "transaction" in parts[0].lower() or "asset" in parts[0].lower():
        return None
    if _looks_like_date(parts[0]):
        tx_date, asset_name, ticker, tx_type, amount = parts[:5]
        owner = parts[5] if len(parts) > 5 else "self"
    else:
        asset_name, ticker, tx_type, tx_date, amount = parts[:5]
        owner = parts[5] if len(parts) > 5 else "self"
    return {
        "tx_date": tx_date,
        "ticker": ticker or None,
        "asset_name": asset_name,
        "tx_type": tx_type,
        "amount": amount,
        "owner": owner or "self",
    }


def _parse_freeform_row(line: str) -> dict | None:
    date_match = re.search(r"\b(\d{1,2}/\d{1,2}/\d{2,4}|\d{4}-\d{2}-\d{2})\b", line)
    amount_match = re.search(r"(\$?\d[\d,]*\s*(?:-|to|–)\s*\$?\d[\d,]*|Over\s+\$?\d[\d,]*|\$?\d[\d,]*\+?)", line, flags=re.IGNORECASE)
    type_match = re.search(r"\b(Purchase|Sale(?:\s*\(Full\)|\s*\(Partial\))?|Exchange|Buy|Sell)\b", line, flags=re.IGNORECASE)
    if not date_match or not amount_match or not type_match:
        return None
    ticker = None
    ticker_match = re.search(r"\(([A-Z][A-Z0-9.\-]{0,9})\)", line)
    if ticker_match:
        ticker = ticker_match.group(1)
    else:
        ticker_match = re.search(r"\b(?:ticker|symbol)\s*[:\-]\s*([A-Z][A-Z0-9.\-]{0,9})\b", line, flags=re.IGNORECASE)
        if ticker_match:
            ticker = ticker_match.group(1)
    asset_part = line[: type_match.start()]
    asset_part = asset_part.replace(date_match.group(1), " ")
    asset_part = re.sub(r"\([^)]*\)", " ", asset_part)
    asset_name = re.sub(r"\s+", " ", asset_part).strip(" -;,") or ticker or "Unknown"
    return {
        "tx_date": date_match.group(1),
        "ticker": ticker,
        "asset_name": asset_name,
        "tx_type": type_match.group(1),
        "amount": amount_match.group(1),
        "owner": "self",
    }


def _parse_house_table_blocks(lines: list[str]) -> list[dict]:
    records: list[dict] = []
    block: list[str] = []
    for line in lines:
        if _is_house_table_boundary(line):
            parsed = _parse_house_transaction_block(block)
            if parsed:
                records.append(parsed)
            block = []
            continue
        if _is_house_table_noise(line):
            continue
        block.append(line)
    parsed = _parse_house_transaction_block(block)
    if parsed:
        records.append(parsed)
    return records


def _parse_house_transaction_block(block: list[str]) -> dict | None:
    if not block:
        return None
    text = re.sub(r"\s+", " ", " ".join(block)).strip()
    pattern = re.compile(
        r"^(?P<asset>.+?)\s*(?:\[(?P<asset_code>[A-Z]{2})\])?\s+"
        r"(?P<tx_type>P|S(?:\s*\(partial\))?|E)\s+"
        r"(?P<tx_date>\d{1,2}/\d{1,2}/\d{4})\s*"
        r"(?P<notification_date>\d{1,2}/\d{1,2}/\d{4})?\s*"
        r"(?P<amount>(?:Over\s+)?\$?\s*\d[\d,]*(?:\.\d+)?(?:\s*(?:-|to|–)\s*\$?\s*\d[\d,]*(?:\.\d+)?)?)",
        flags=re.IGNORECASE,
    )
    match = pattern.search(text)
    if not match:
        return None
    asset = match.group("asset").strip(" -;,")
    owner, asset = _extract_house_owner(asset)
    ticker = _extract_house_ticker(asset)
    asset_name = _clean_house_asset_name(asset, ticker)
    tx_type = _normalize_house_tx_type(match.group("tx_type"))
    amount = re.sub(r"\s+", " ", match.group("amount").replace("–", "-")).strip()
    amount = re.sub(r"\s*-\s*", " - ", amount)
    asset_code = (match.group("asset_code") or "").upper()
    parsed = {
        "tx_date": match.group("tx_date"),
        "ticker": ticker,
        "asset_name": asset_name,
        "tx_type": tx_type,
        "amount": amount,
        "owner": owner,
        "raw_ref": text,
    }
    asset_type = _asset_type_from_house_code(asset_code, asset_name)
    if asset_type:
        parsed["asset_type"] = asset_type
    return parsed


def _is_house_table_boundary(line: str) -> bool:
    text = line.strip()
    if text.startswith("* For the complete list"):
        return True
    if text.startswith("Filing ID #"):
        return True
    if re.match(r"^(Filing Status|Subholding Of|Description|Comments?|Location)\s*:", text, flags=re.IGNORECASE):
        return True
    if re.match(r"^(F\s*S|S\s*O|D|C|L)\s*:", text):
        return True
    if "CERTIFY" in text or text.startswith("Digitally Signed:"):
        return True
    return False


def _is_house_table_noise(line: str) -> bool:
    text = line.strip()
    lower = text.lower()
    if _is_header_line(text):
        return True
    if lower in {"periodic transaction report", "id owner asset transaction"}:
        return True
    if text in {"Type", "Date Notification", "Date", "Amount Cap.", "Gains >", "$200?", "Yes No"}:
        return True
    if lower.startswith(("clerk of the house", "name:", "status:", "state/district:")):
        return True
    if re.fullmatch(r"[A-Z](?:\s+[A-Z]){1,}", text):
        return True
    return False


def _extract_house_owner(asset: str) -> tuple[str, str]:
    owner_codes = {"DC": "dependent", "JT": "joint", "SP": "spouse"}
    parts = asset.split(maxsplit=1)
    if parts and parts[0].upper() in {"T"} and len(parts) > 1:
        asset = parts[1]
    parts = asset.split(maxsplit=1)
    if parts and parts[0].upper() in owner_codes and len(parts) > 1:
        return owner_codes[parts[0].upper()], parts[1]
    return "self", asset


def _extract_house_ticker(asset: str) -> str | None:
    matches = re.findall(r"\(([A-Z][A-Z0-9.\-]{0,9})\)", asset)
    return matches[-1] if matches else None


def _clean_house_asset_name(asset: str, ticker: str | None) -> str:
    if ticker:
        asset = re.sub(rf"\s*\({re.escape(ticker)}\)\s*", " ", asset)
    asset = re.sub(r"\s+", " ", asset)
    return asset.strip(" -;,") or ticker or "Unknown"


def _normalize_house_tx_type(value: str) -> str:
    text = re.sub(r"\s+", " ", value.strip().upper())
    if text == "P":
        return "Purchase"
    if text.startswith("S"):
        return "Sale (Partial)" if "PARTIAL" in text else "Sale"
    if text == "E":
        return "Exchange"
    return value


def _asset_type_from_house_code(code: str, asset_name: str) -> str | None:
    if code == "ST":
        return "stock"
    if code == "EF":
        return "etf"
    if code == "GS":
        return "bond"
    if code == "OT" and re.search(r"\b(option|call|put)\b", asset_name, flags=re.IGNORECASE):
        return "option"
    if code in {"CS", "OI", "OT"}:
        return "other"
    return None


def _parse_index_payload(payload: dict) -> dict | None:
    tx_date = payload.get("transactiondate") or payload.get("transaction_date")
    amount = payload.get("amount") or payload.get("amountrange")
    tx_type = payload.get("transactiontype") or payload.get("type")
    asset = payload.get("asset") or payload.get("assetname")
    if not (tx_date and amount and tx_type and asset):
        return None
    return {
        "tx_date": tx_date,
        "ticker": payload.get("ticker") or payload.get("symbol"),
        "asset_name": asset,
        "tx_type": tx_type,
        "amount": amount,
        "owner": payload.get("owner") or "self",
    }


def _looks_like_date(value: str) -> bool:
    return bool(re.match(r"^\d{1,4}[/-]\d{1,2}[/-]\d{1,4}$", value.strip()))
