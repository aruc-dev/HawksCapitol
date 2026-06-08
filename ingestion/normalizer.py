from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime

from core.models import Disclosure, Transaction, parse_date
from sources.ticker_resolver import TickerResolver


def parse_amount_range(text: str) -> tuple[float, float, float]:
    values = [float(part.replace(",", "")) for part in re.findall(r"\$?([0-9][0-9,]*)", text or "")]
    if not values:
        return 0.0, 0.0, 0.0
    if len(values) == 1:
        return values[0], values[0], values[0]
    low, high = values[0], values[1]
    return low, high, (low + high) / 2


def classify_asset_type(asset_name: str, option_meta: dict | None = None) -> str:
    text = asset_name.lower()
    if option_meta or " call" in text or " put" in text:
        return "option"
    if "etf" in text or "fund" in text:
        return "etf"
    if "bond" in text:
        return "bond"
    return "stock"


def normalize_tx_type(value: str) -> str:
    text = (value or "").lower()
    if "purchase" in text or "buy" in text:
        return "buy"
    if "sale" in text or "sell" in text:
        return "sell"
    if "exchange" in text:
        return "exchange"
    return text or "unknown"


def make_dedup_key(member_id: str, ticker: str | None, tx_type: str, tx_date, amount_mid: float) -> str:
    key = f"{member_id}|{ticker}|{tx_type}|{tx_date}|{round(amount_mid, 2)}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


def normalize_record(record: dict, resolver: TickerResolver | None = None) -> tuple[Disclosure, Transaction]:
    resolver = resolver or TickerResolver()
    filing_date = parse_date(record.get("filing_date")) or parse_date(record.get("filed_date"))
    tx_date = parse_date(record.get("tx_date") or record.get("transaction_date") or record.get("transaction_date_"))
    if filing_date is None or tx_date is None:
        raise ValueError("record requires filing_date and tx_date")
    member_name = record.get("member_name") or record.get("name") or "Unknown"
    member_id = record.get("member_id") or re.sub(r"[^a-z0-9]+", "-", member_name.lower()).strip("-")
    doc_id = str(record.get("doc_id") or record.get("document_id") or make_dedup_key(member_id, None, "", filing_date, 0))
    ticker = resolver.resolve(record.get("asset_name") or record.get("asset") or "", record.get("ticker") or record.get("symbol"))
    amount_min, amount_max, amount_mid = parse_amount_range(record.get("amount") or record.get("amount_range") or "")
    tx_type = normalize_tx_type(record.get("tx_type") or record.get("transaction_type") or record.get("type") or "")
    asset_name = record.get("asset_name") or record.get("asset") or record.get("asset_name_raw") or ticker or "Unknown"
    asset_type = classify_asset_type(asset_name, record.get("option_meta"))
    price_tx = record.get("price_on_tx_date")
    price_filing = record.get("price_on_filing_date")
    filing_gap_pct = None
    if price_tx and price_filing:
        filing_gap_pct = (float(price_filing) - float(price_tx)) / float(price_tx)
    lag = (filing_date - tx_date).days
    dedup_key = make_dedup_key(member_id, ticker, tx_type, tx_date, amount_mid)
    disclosure = Disclosure(
        doc_id=doc_id,
        source=record.get("source", "unknown"),
        member_id=member_id,
        filing_date=filing_date,
        ingested_at=datetime.now(UTC),
        url=record.get("url", ""),
        parse_confidence=float(record.get("parse_confidence", 1.0)),
        amends_doc_id=record.get("amends_doc_id"),
    )
    tx = Transaction(
        tx_id=str(record.get("tx_id") or dedup_key),
        doc_id=doc_id,
        member_id=member_id,
        asset_name_raw=asset_name,
        ticker=ticker,
        asset_type=asset_type,
        tx_type=tx_type,
        tx_date=tx_date,
        filing_date=filing_date,
        amount_min=amount_min,
        amount_max=amount_max,
        amount_mid=amount_mid,
        owner=record.get("owner") or "self",
        source=record.get("source", "unknown"),
        source_quality=record.get("source_quality", "official"),
        parse_confidence=float(record.get("parse_confidence", 1.0)),
        option_meta=record.get("option_meta"),
        filing_lag_days=lag,
        price_on_tx_date=float(price_tx) if price_tx else None,
        price_on_filing_date=float(price_filing) if price_filing else None,
        filing_gap_pct=filing_gap_pct,
        dedup_key=dedup_key,
        raw_ref=record.get("raw_ref", ""),
    )
    return disclosure, tx


def normalize_records(records: list[dict], resolver: TickerResolver | None = None) -> tuple[list[Disclosure], list[Transaction]]:
    disclosures = []
    transactions = []
    seen_docs = set()
    for record in records:
        disclosure, tx = normalize_record(record, resolver)
        if disclosure.doc_id not in seen_docs:
            disclosures.append(disclosure)
            seen_docs.add(disclosure.doc_id)
        transactions.append(tx)
    return disclosures, transactions
