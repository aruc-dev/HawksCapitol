from __future__ import annotations

from datetime import date

from core.models import ExitDecision, MarketSnapshot, Position, parse_date


def evaluate_exit(position: Position, market: MarketSnapshot, cfg: dict, effective_tx_date: date, member_score: float = 1.0) -> ExitDecision | None:
    exits = cfg["exits"]
    symbol = position.ticker.upper()
    stale = symbol in market.stale_symbols
    price = market.effective_price(symbol)
    if price is None:
        return ExitDecision(position.ticker, "stale_price_alert", "alert", None, 5)
    if position.asset_type == "option":
        option_exit = _evaluate_option_exit(position, market, exits, price)
        if option_exit:
            return option_exit
    if price <= position.stop_price:
        return ExitDecision(position.ticker, "hard_stop_loss", "exit", price, 1)
    if price >= position.target_price:
        action = "scale_out" if exits.get("profit_scale_out_pct", 1.0) < 1.0 else "exit"
        return ExitDecision(position.ticker, "profit_target", action, price, 2)
    if price > position.trail_high:
        position.trail_high = price
    if price <= position.trail_high * (1 - exits["trailing_stop_pct"]) and position.trail_high >= position.entry_price * (1 + exits["trail_activation_pct"]):
        return ExitDecision(position.ticker, "trailing_stop", "exit", price, 3)
    if (market.as_of - effective_tx_date).days >= exits["max_alpha_age_days"]:
        return ExitDecision(position.ticker, "alpha_decay_time_stop", "exit", price, 4)
    events = market.events.get(symbol, set())
    if "member_sell" in events:
        return ExitDecision(position.ticker, "member_sell_filed", "exit", price, 5)
    if not market.regime_ok:
        return ExitDecision(position.ticker, "regime_exit", "exit", price, 5)
    if "earnings" in events:
        return ExitDecision(position.ticker, "earnings_blackout_exit", "exit", price, 5)
    if "corporate_action" in events:
        return ExitDecision(position.ticker, "corporate_action_exit", "exit", price, 5)
    if member_score <= exits["conviction_drop_exit_score"]:
        return ExitDecision(position.ticker, "conviction_decay", "exit", price, 6)
    if (market.as_of - position.entry_date).days >= exits["max_hold_days"]:
        return ExitDecision(position.ticker, "max_hold_cap", "exit", price, 7)
    if stale:
        return ExitDecision(position.ticker, "stale_price_alert", "alert", price, 8)
    return None


def _evaluate_option_exit(position: Position, market: MarketSnapshot, exits: dict, price: float) -> ExitDecision | None:
    option_meta = position.option_meta or {}
    expiry_text = option_meta.get("expiry")
    if expiry_text:
        expiry = parse_date(expiry_text)
        if expiry and (expiry - market.as_of).days <= exits.get("min_option_dte_exit_days", 7):
            return ExitDecision(position.ticker, "option_time_to_expiry", "exit", price, 1)
    if price >= position.entry_price * (1 + exits.get("option_profit_target_pct", 0.5)):
        return ExitDecision(position.ticker, "option_profit_target", "exit", price, 2)
    metrics = market.option_metrics.get(position.ticker.upper(), {})
    delta = abs(metrics.get("delta", 1.0))
    if delta <= exits.get("min_option_delta_abs", 0.15):
        return ExitDecision(position.ticker, "option_delta_decay", "exit", price, 4)
    return None
