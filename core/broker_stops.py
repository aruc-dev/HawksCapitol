from __future__ import annotations

from core.models import Position


def protective_stop_order_id(position: Position) -> str:
    return f"hc-stop-{position.trade_id}-{position.ticker}"


def planned_protective_stop(position: Position) -> dict:
    return {
        "client_order_id": protective_stop_order_id(position),
        "ticker": position.ticker,
        "side": "sell",
        "qty": position.qty,
        "stop_price": position.stop_price,
        "asset_type": position.asset_type,
    }


def sync_protective_stops(positions: list[Position]) -> list[dict]:
    return [planned_protective_stop(position) for position in positions if position.status == "open" and position.qty > 0]
