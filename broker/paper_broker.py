from __future__ import annotations

from core.models import BrokerPosition, Order, OrderResult


class PaperBroker:
    def __init__(self) -> None:
        self.orders: dict[str, OrderResult] = {}
        self._positions: dict[str, BrokerPosition] = {}

    def submit(self, order: Order) -> OrderResult:
        if order.client_order_id in self.orders:
            return self.orders[order.client_order_id]
        result = OrderResult(order.client_order_id, order.ticker, order.side, order.qty, "accepted")
        self.orders[order.client_order_id] = result
        if order.side == "buy":
            existing = self._positions.get(order.ticker)
            qty = order.qty + (existing.qty if existing else 0)
            fill_price = order.limit_price or (existing.avg_entry_price if existing else 0.0)
            if existing and qty:
                avg = ((existing.qty * existing.avg_entry_price) + (order.qty * fill_price)) / qty
            else:
                avg = fill_price
            self._positions[order.ticker] = BrokerPosition(order.ticker, qty, avg, order.asset_type)
        return result

    def positions(self) -> list[BrokerPosition]:
        return list(self._positions.values())

    def reconcile(self, trade_log: list[dict]) -> dict:
        broker_symbols = {p.ticker for p in self.positions()}
        log_symbols = {row.get("ticker") for row in trade_log if row.get("status") == "open"}
        return {
            "missing_in_broker": sorted(log_symbols - broker_symbols),
            "missing_in_log": sorted(broker_symbols - log_symbols),
        }
