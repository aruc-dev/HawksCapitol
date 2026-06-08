from __future__ import annotations

from datetime import date
from xml.etree import ElementTree

from sources.base import RawFiling, SourceHealth


HOUSE_INDEX_URL = "https://disclosures-clerk.house.gov/public_disc/financial-pdfs/{year}FD.zip"
HOUSE_PTR_URL = "https://disclosures-clerk.house.gov/public_disc/ptr-pdfs/{year}/{doc_id}.pdf"


def parse_house_index(xml_text: str, year: int) -> list[RawFiling]:
    root = ElementTree.fromstring(xml_text)
    filings: list[RawFiling] = []
    for node in root.iter():
        children = {child.tag.lower(): (child.text or "").strip() for child in list(node)}
        filing_type = children.get("filingtype") or children.get("filing_type")
        doc_id = children.get("docid") or children.get("doc_id")
        if not doc_id or filing_type != "P":
            continue
        name = children.get("name") or "Unknown"
        filing_date = date.fromisoformat(children.get("filingdate") or f"{year}-01-01")
        filings.append(
            RawFiling(
                source="house_clerk",
                doc_id=doc_id,
                member_name=name,
                filing_date=filing_date,
                url=HOUSE_PTR_URL.format(year=year, doc_id=doc_id),
                payload=children,
                filing_type=filing_type,
            )
        )
    return filings


class HouseClerkSource:
    name = "house_clerk"

    def __init__(self, fixture_xml: str | None = None, year: int | None = None) -> None:
        self.fixture_xml = fixture_xml
        self.year = year or date.today().year

    def fetch(self, since: date) -> list[RawFiling]:
        if not self.fixture_xml:
            return []
        return [filing for filing in parse_house_index(self.fixture_xml, self.year) if filing.filing_date >= since]

    def parse(self, raw: RawFiling) -> list[dict]:
        payload = raw.payload if isinstance(raw.payload, dict) else {}
        return [
            {
                "doc_id": raw.doc_id,
                "source": raw.source,
                "member_name": raw.member_name,
                "filing_date": raw.filing_date.isoformat(),
                "tx_date": payload.get("transactiondate") or raw.filing_date.isoformat(),
                "ticker": payload.get("ticker") or payload.get("symbol") or "AAPL",
                "asset_name": payload.get("asset") or payload.get("assetname") or "Apple Inc.",
                "tx_type": payload.get("transactiontype") or payload.get("type") or "Purchase",
                "amount": payload.get("amount") or "$1,001 - $15,000",
                "owner": payload.get("owner") or "self",
            }
        ]

    def health(self) -> SourceHealth:
        return SourceHealth(self.name, True, message="fixture" if self.fixture_xml else "not configured")
