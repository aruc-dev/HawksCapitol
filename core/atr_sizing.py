from __future__ import annotations


def calculate_position_qty(
    account_equity: float,
    risk_per_trade_pct: float,
    entry_price: float,
    stop_price: float,
    max_position_pct: float,
    conviction_scale: float = 1.0,
) -> float:
    risk_dollars = account_equity * risk_per_trade_pct * max(0.0, min(conviction_scale, 1.0))
    per_share_risk = max(entry_price - stop_price, entry_price * 0.01)
    qty_by_risk = risk_dollars / per_share_risk
    qty_by_cap = (account_equity * max_position_pct) / entry_price
    return max(0.0, round(min(qty_by_risk, qty_by_cap), 4))
