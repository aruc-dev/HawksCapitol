from __future__ import annotations

from difflib import SequenceMatcher
import re

from core.models import Transaction


SOURCE_RANK = {"official": 3, "third_party_verified": 2, "third_party_only": 1}


def dedupe_transactions(transactions: list[Transaction]) -> list[Transaction]:
    winners: list[Transaction] = []
    by_doc_id: dict[str, int] = {}
    for tx in sorted(transactions, key=lambda item: (item.filing_date, item.doc_id, item.tx_id)):
        if tx.amends_doc_id and tx.amends_doc_id in by_doc_id:
            idx = by_doc_id[tx.amends_doc_id]
            winners[idx] = _prefer(winners[idx], tx)
            by_doc_id[tx.doc_id] = idx
            continue
        idx = _find_duplicate_index(winners, tx)
        if idx is None:
            by_doc_id[tx.doc_id] = len(winners)
            winners.append(tx)
        else:
            winners[idx] = _prefer(winners[idx], tx)
            by_doc_id[tx.doc_id] = idx
    return winners


def same_disclosed_trade(left: Transaction, right: Transaction) -> bool:
    if left.member_id != right.member_id or left.tx_type != right.tx_type or left.tx_date != right.tx_date:
        return False
    if abs(left.amount_mid - right.amount_mid) > 1:
        return False
    if left.ticker and right.ticker and left.ticker.upper() == right.ticker.upper():
        return True
    return _similarity(left.asset_name_raw, right.asset_name_raw) >= 0.9


def reconciliation_key(tx: Transaction) -> str:
    asset = tx.ticker or _normalize_asset(tx.asset_name_raw)
    return f"{tx.member_id}|{asset}|{tx.tx_type}|{tx.tx_date}|{round(tx.amount_mid, 2)}"


def _find_duplicate_index(winners: list[Transaction], tx: Transaction) -> int | None:
    for idx, existing in enumerate(winners):
        if existing.dedup_key == tx.dedup_key or same_disclosed_trade(existing, tx):
            return idx
    return None


def _prefer(existing: Transaction, candidate: Transaction) -> Transaction:
    existing_rank = SOURCE_RANK.get(existing.source_quality, 0)
    candidate_rank = SOURCE_RANK.get(candidate.source_quality, 0)
    if candidate.amends_doc_id == existing.doc_id:
        return candidate
    if candidate_rank != existing_rank:
        return candidate if candidate_rank > existing_rank else existing
    if candidate.parse_confidence != existing.parse_confidence:
        return candidate if candidate.parse_confidence > existing.parse_confidence else existing
    return candidate if candidate.filing_date >= existing.filing_date else existing


def _normalize_asset(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _similarity(left: str, right: str) -> float:
    return SequenceMatcher(None, _normalize_asset(left), _normalize_asset(right)).ratio()
