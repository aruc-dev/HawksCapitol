from __future__ import annotations

from core.models import Position


def open_position_weights(positions: list[Position], account_equity: float) -> dict[str, float]:
    weights = {}
    for pos in positions:
        if pos.status == "open":
            weights[pos.ticker] = (pos.qty * pos.entry_price) / account_equity
    return weights
