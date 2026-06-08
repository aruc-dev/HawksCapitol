from __future__ import annotations

from core.models import Transaction
from ingestion.dedupe import dedupe_transactions, same_disclosed_trade


def reconcile_transactions(transactions: list[Transaction]) -> tuple[list[Transaction], list[str]]:
    warnings: list[str] = []
    groups: list[list[Transaction]] = []
    for tx in transactions:
        for group in groups:
            if any(existing.dedup_key == tx.dedup_key or same_disclosed_trade(existing, tx) for existing in group):
                group.append(tx)
                break
        else:
            groups.append([tx])
    winners: list[Transaction] = []
    for group in groups:
        official = [tx for tx in group if tx.source_quality == "official"]
        winner = max(official or group, key=lambda tx: (tx.parse_confidence, tx.filing_date))
        if len(group) > 1:
            sources = ",".join(sorted({tx.source for tx in group}))
            warnings.append(f"reconciled {len(group)} records for {winner.dedup_key}; winner={winner.source}; sources={sources}")
            warnings.extend(_conflict_warnings(group, winner))
        winners.append(winner)
    return dedupe_transactions(winners), warnings


def _conflict_warnings(group: list[Transaction], winner: Transaction) -> list[str]:
    warnings = []
    for tx in group:
        if tx is winner:
            continue
        if tx.ticker != winner.ticker:
            warnings.append(f"ticker conflict for {winner.dedup_key}: {winner.source}={winner.ticker} {tx.source}={tx.ticker}")
        if tx.amount_min != winner.amount_min or tx.amount_max != winner.amount_max:
            warnings.append(f"amount conflict for {winner.dedup_key}: {winner.source} wins over {tx.source}")
    return warnings
