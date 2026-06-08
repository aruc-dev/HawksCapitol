from __future__ import annotations

from dataclasses import fields
from datetime import date
from pathlib import Path

from core.models import Transaction, parse_date
from ingestion.storage import read_json


DEFAULT_BACKTEST_DATASET = Path("data/backtest/official_house_6mo/transactions.json")
TRANSACTION_FIELDS = {field.name for field in fields(Transaction)}


def load_transactions(path: str | Path = DEFAULT_BACKTEST_DATASET) -> list[Transaction]:
    rows = read_json(path, None)
    if rows is None:
        raise FileNotFoundError(f"backtest dataset not found: {path}")
    if not isinstance(rows, list):
        raise ValueError(f"backtest dataset must be a list: {path}")
    return [_transaction_from_row(row) for row in rows]


def infer_as_of(transactions: list[Transaction]) -> date:
    if not transactions:
        raise ValueError("backtest dataset has no transactions")
    return max(tx.filing_date for tx in transactions)


def load_sector_map(path: str | Path = "config/sectors.json") -> dict[str, str]:
    rows = read_json(path, {})
    if not isinstance(rows, dict):
        raise ValueError(f"sector map must be a JSON object: {path}")
    return {str(symbol).upper(): str(sector) for symbol, sector in rows.items()}


def _transaction_from_row(row: object) -> Transaction:
    if not isinstance(row, dict):
        raise ValueError("backtest transaction rows must be objects")
    payload = {key: value for key, value in row.items() if key in TRANSACTION_FIELDS}
    payload["tx_date"] = _required_date(payload.get("tx_date"), "tx_date")
    payload["filing_date"] = _required_date(payload.get("filing_date"), "filing_date")
    return Transaction(**payload)


def _required_date(value: object, field_name: str) -> date:
    parsed = parse_date(value)  # type: ignore[arg-type]
    if parsed is None:
        raise ValueError(f"backtest transaction has invalid or missing {field_name}")
    return parsed
