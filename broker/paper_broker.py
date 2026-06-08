from __future__ import annotations

from pathlib import Path

from core.models import BrokerPosition, Order, OrderResult
from ingestion.storage import read_json, write_json


class PaperBroker:
    def __init__(self, state_path: str | Path | None = None) -> None:
        self.state_path = Path(state_path) if state_path else None
        self.orders: dict[str, OrderResult] = {}
        self._positions: dict[str, BrokerPosition] = {}
        self._load()

    def submit(self, order: Order) -> OrderResult:
        if order.client_order_id in self.orders:
            return self.orders[order.client_order_id]
        result = OrderResult(order.client_order_id, order.ticker, order.side, order.qty, "accepted")
        self.orders[order.client_order_id] = result
        if order.side == "buy":
            self._apply_buy(order)
        elif order.side == "sell":
            self._apply_sell(order)
        self._save()
        return result

    def positions(self) -> list[BrokerPosition]:
        return list(self._positions.values())

    def reconcile(self, trade_log: list[dict]) -> dict:
        broker_symbols = {p.ticker for p in self.positions() if p.qty != 0}
        log_symbols = {row.get("ticker") for row in trade_log if row.get("status") in {"open", "accepted"} or row.get("side") == "buy"}
        return {
            "missing_in_broker": sorted(symbol for symbol in log_symbols - broker_symbols if symbol),
            "missing_in_log": sorted(broker_symbols - log_symbols),
            "broker_positions": sorted(broker_symbols),
        }

    def _apply_buy(self, order: Order) -> None:
        existing = self._positions.get(order.ticker)
        qty = order.qty + (existing.qty if existing else 0)
        fill_price = order.limit_price or (existing.avg_entry_price if existing else 0.0)
        if existing and qty:
            avg = ((existing.qty * existing.avg_entry_price) + (order.qty * fill_price)) / qty
        else:
            avg = fill_price
        self._positions[order.ticker] = BrokerPosition(order.ticker, qty, avg, order.asset_type)

    def _apply_sell(self, order: Order) -> None:
        existing = self._positions.get(order.ticker)
        if not existing:
            return
        qty = max(0.0, existing.qty - order.qty)
        if qty:
            self._positions[order.ticker] = BrokerPosition(order.ticker, qty, existing.avg_entry_price, existing.asset_type)
        else:
            self._positions.pop(order.ticker, None)

    def _load(self) -> None:
        if not self.state_path:
            return
        state = read_json(self.state_path, {"orders": [], "positions": []})
        self.orders = {
            row["client_order_id"]: OrderResult(**row)
            for row in state.get("orders", [])
        }
        self._positions = {
            row["ticker"]: BrokerPosition(**row)
            for row in state.get("positions", [])
        }

    def _save(self) -> None:
        if not self.state_path:
            return
        write_json(
            self.state_path,
            {
                "orders": list(self.orders.values()),
                "positions": list(self._positions.values()),
            },
        )
