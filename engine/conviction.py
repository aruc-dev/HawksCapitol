from __future__ import annotations

from core.models import MemberScore, Transaction


def conviction_score(tx: Transaction, member_score: MemberScore | None, cluster_count: int = 1, committee_relevant: bool = False) -> float:
    base = member_score.score if member_score else 0.0
    amount_tier = min(0.20, tx.amount_mid / 1_000_000 * 0.20)
    cluster_bonus = min(0.20, max(0, cluster_count - 1) * 0.05)
    committee_bonus = 0.05 if committee_relevant else 0.0
    return round(min(1.0, base + amount_tier + cluster_bonus + committee_bonus), 4)
