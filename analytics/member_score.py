from __future__ import annotations

from datetime import date

from core.models import MemberScore, Transaction


def compute_member_scores(transactions: list[Transaction], as_of: date, min_sample: int = 3) -> dict[str, MemberScore]:
    visible = [tx for tx in transactions if tx.filing_date <= as_of and tx.tx_type == "buy"]
    by_member: dict[str, list[Transaction]] = {}
    for tx in visible:
        by_member.setdefault(tx.member_id, []).append(tx)
    scores: dict[str, MemberScore] = {}
    for member_id, rows in by_member.items():
        n = len(rows)
        avg_lag = sum(tx.filing_lag_days for tx in rows) / n
        sample_quality = min(1.0, n / min_sample)
        latency_score = max(0.0, 1.0 - avg_lag / 60)
        amount_score = min(1.0, sum(tx.amount_mid for tx in rows) / max(1.0, n * 50000))
        parse_score = sum(tx.parse_confidence for tx in rows) / n
        score = round((0.35 * sample_quality) + (0.25 * latency_score) + (0.25 * amount_score) + (0.15 * parse_score), 4)
        if n < min_sample:
            score = min(score, 0.49)
        scores[member_id] = MemberScore(
            member_id=member_id,
            as_of_date=as_of,
            n_trades=n,
            hit_rate=0.0,
            avg_alpha_30d=0.0,
            avg_alpha_90d=0.0,
            median_hold=0,
            filing_latency_days=round(avg_lag, 2),
            sector_concentration=0.0,
            sample_quality=round(sample_quality, 4),
            score=score,
        )
    return scores
