from __future__ import annotations

from datetime import date

from core.models import Transaction


def visible_transactions(transactions: list[Transaction], as_of: date) -> list[Transaction]:
    return sorted((tx for tx in transactions if tx.filing_date <= as_of), key=lambda tx: (tx.filing_date, tx.tx_id))
