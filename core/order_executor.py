from __future__ import annotations

from core.live_mode_guard import assert_live_allowed
from core.models import Order, OrderResult, Signal
from core.order_governor import OrderGovernor


def order_from_signal(signal: Signal, account_equity: float, price: float) -> Order:
    notional = account_equity * signal.target_weight_pct
    qty = round(notional / price, 4) if price > 0 else 0
    return Order(
        client_order_id=f"hc-{signal.signal_id}",
        ticker=signal.ticker,
        side="buy" if signal.side == "copy_buy" else "sell",
        qty=qty,
        asset_type=signal.asset_type,
        limit_price=price,
    )


def execute_signal(signal: Signal, broker, cfg: dict, price: float, governor: OrderGovernor, human_approved: bool = False) -> OrderResult:
    assert_live_allowed(cfg, human_approved=human_approved)
    if signal.blocked_reason:
        return OrderResult(f"hc-{signal.signal_id}", signal.ticker, signal.side, 0, "blocked", signal.blocked_reason)
    if signal.asset_type == "option" and not cfg.get("execution", {}).get("options_enabled", False):
        return OrderResult(f"hc-{signal.signal_id}", signal.ticker, signal.side, 0, "blocked", "options_disabled")
    order = order_from_signal(signal, cfg["risk"]["account_equity"], price)
    governor.check(order, price)
    result = broker.submit(order)
    governor.record()
    return result
