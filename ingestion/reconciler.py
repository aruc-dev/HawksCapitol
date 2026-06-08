from __future__ import annotations

from core.models import Transaction
from ingestion.dedupe import dedupe_transactions


def reconcile_transactions(transactions: list[Transaction]) -> tuple[list[Transaction], list[str]]:
    warnings: list[str] = []
    grouped: dict[str, list[Transaction]] = {}
    for tx in transactions:
        grouped.setdefault(tx.dedup_key, []).append(tx)
    winners: list[Transaction] = []
    for key, group in grouped.items():
        official = [tx for tx in group if tx.source_quality == "official"]
        winner = max(official or group, key=lambda tx: tx.parse_confidence)
        if len(group) > 1:
            warnings.append(f"reconciled {len(group)} records for {key}; winner={winner.source}")
        winners.append(winner)
    return dedupe_transactions(winners), warnings
