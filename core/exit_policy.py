from __future__ import annotations

from datetime import date

from core.models import ExitDecision, MarketSnapshot, Position


def evaluate_exit(position: Position, market: MarketSnapshot, cfg: dict, effective_tx_date: date, member_score: float = 1.0) -> ExitDecision | None:
    price = market.price(position.ticker)
    exits = cfg["exits"]
    if price is None:
        return ExitDecision(position.ticker, "stale_price_alert", "alert", None, 5)
    if price <= position.stop_price:
        return ExitDecision(position.ticker, "hard_stop_loss", "exit", price, 1)
    if price >= position.target_price:
        return ExitDecision(position.ticker, "profit_target", "exit", price, 2)
    if price > position.trail_high:
        position.trail_high = price
    if price <= position.trail_high * (1 - exits["trailing_stop_pct"]) and position.trail_high >= position.entry_price * (1 + exits["trail_activation_pct"]):
        return ExitDecision(position.ticker, "trailing_stop", "exit", price, 3)
    if (market.as_of - effective_tx_date).days >= exits["max_alpha_age_days"]:
        return ExitDecision(position.ticker, "alpha_decay_time_stop", "exit", price, 4)
    if not market.regime_ok:
        return ExitDecision(position.ticker, "regime_exit", "exit", price, 5)
    if member_score <= exits["conviction_drop_exit_score"]:
        return ExitDecision(position.ticker, "conviction_decay", "exit", price, 6)
    if (market.as_of - position.entry_date).days >= exits["max_hold_days"]:
        return ExitDecision(position.ticker, "max_hold_cap", "exit", price, 7)
    return None
