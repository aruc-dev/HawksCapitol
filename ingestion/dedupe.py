from __future__ import annotations

from core.models import Transaction


def dedupe_transactions(transactions: list[Transaction]) -> list[Transaction]:
    by_key: dict[str, Transaction] = {}
    for tx in transactions:
        existing = by_key.get(tx.dedup_key)
        if existing is None or tx.parse_confidence >= existing.parse_confidence:
            by_key[tx.dedup_key] = tx
    return list(by_key.values())
