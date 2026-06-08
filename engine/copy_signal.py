from __future__ import annotations

from datetime import UTC, date, datetime

from analytics.alpha_decay import freshness_score
from core.models import MemberScore, Signal, Transaction
from core.risk_manager import portfolio_caps_allow
from engine.conviction import conviction_score
from engine.entry_quality import entry_quality_score


def build_copy_signals(
    transactions: list[Transaction],
    member_scores: dict[str, MemberScore],
    cfg: dict,
    sector_map: dict[str, str],
    as_of: date,
    open_weights: dict[str, float] | None = None,
) -> list[Signal]:
    open_weights = dict(open_weights or {})
    output: list[Signal] = []
    buys = [tx for tx in transactions if tx.tx_type == "buy" and tx.filing_date <= as_of]
    cluster_counts: dict[str, int] = {}
    for tx in buys:
        if tx.ticker:
            cluster_counts[tx.ticker] = cluster_counts.get(tx.ticker, 0) + 1
    for tx in buys:
        if not tx.ticker:
            output.append(_blocked(tx, "unresolved_ticker"))
            continue
        fresh = freshness_score(tx.tx_date, as_of, cfg["exits"]["max_alpha_age_days"])
        if fresh < cfg["signals"]["min_freshness_score"]:
            output.append(_blocked(tx, "freshness_below_threshold", fresh))
            continue
        member_score = member_scores.get(tx.member_id)
        if not member_score or member_score.score < cfg["signals"]["min_member_score"]:
            output.append(_blocked(tx, "member_score_below_threshold", fresh))
            continue
        conviction = conviction_score(tx, member_score, cluster_counts.get(tx.ticker, 1))
        if conviction < cfg["signals"]["min_conviction_score"]:
            output.append(_blocked(tx, "conviction_below_threshold", fresh, conviction))
            continue
        entry_quality, blocked = entry_quality_score(tx, cfg)
        if blocked:
            output.append(_blocked(tx, blocked, fresh, conviction, entry_quality))
            continue
        target_weight = round(min(cfg["risk"]["max_position_pct"], cfg["risk"]["max_position_pct"] * conviction * fresh * entry_quality), 4)
        ok, reason = portfolio_caps_allow(tx.ticker, target_weight, open_weights, sector_map, cfg)
        if not ok:
            output.append(_blocked(tx, reason or "risk_cap", fresh, conviction, entry_quality))
            continue
        open_weights[tx.ticker] = target_weight
        output.append(
            Signal(
                signal_id=f"sig-{tx.tx_id}",
                created_at=datetime.now(UTC),
                ticker=tx.ticker,
                asset_type=tx.asset_type,
                side="copy_buy",
                source_tx_ids=[tx.tx_id],
                conviction_score=conviction,
                freshness_score=fresh,
                entry_quality_score=entry_quality,
                target_weight_pct=target_weight,
                rationale=f"copy buy from {tx.member_id}; conviction={conviction}; freshness={fresh}; quality={entry_quality}",
            )
        )
    return output


def _blocked(tx: Transaction, reason: str, fresh: float = 0.0, conviction: float = 0.0, quality: float = 0.0) -> Signal:
    return Signal(
        signal_id=f"blocked-{tx.tx_id}",
        created_at=datetime.now(UTC),
        ticker=tx.ticker or "UNRESOLVED",
        asset_type=tx.asset_type,
        side="copy_buy",
        source_tx_ids=[tx.tx_id],
        conviction_score=conviction,
        freshness_score=fresh,
        entry_quality_score=quality,
        target_weight_pct=0.0,
        rationale="candidate blocked",
        blocked_reason=reason,
    )
