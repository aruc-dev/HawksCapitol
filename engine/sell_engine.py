from __future__ import annotations

from datetime import date

from core.exit_policy import evaluate_exit
from core.models import ExitDecision, MarketSnapshot, Position


def evaluate_positions(
    positions: list[Position],
    tx_dates_by_trade: dict[str, date],
    market: MarketSnapshot,
    cfg: dict,
    member_scores: dict[str, float] | None = None,
) -> list[ExitDecision]:
    decisions: list[ExitDecision] = []
    member_scores = member_scores or {}
    for position in positions:
        if position.status != "open":
            continue
        tx_date = tx_dates_by_trade.get(position.trade_id, position.entry_date)
        score = min((member_scores.get(member, 1.0) for member in position.member_ids), default=1.0)
        decision = evaluate_exit(position, market, cfg, tx_date, score)
        if decision:
            decisions.append(decision)
    return decisions
