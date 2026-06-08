from __future__ import annotations

import os

from core.live_mode_guard import assert_live_allowed
from core.models import BrokerPosition, Order, OrderResult


class AlpacaUnavailable(RuntimeError):
    pass


class AlpacaPaperBroker:
    def __init__(self, cfg: dict, human_approved: bool = False) -> None:
        assert_live_allowed(cfg, human_approved=human_approved)
        try:
            from alpaca.trading.client import TradingClient
            from alpaca.trading.requests import MarketOrderRequest
            from alpaca.trading.enums import OrderSide, TimeInForce
        except Exception as exc:
            raise AlpacaUnavailable("alpaca-py is not installed") from exc
        key = os.getenv("ALPACA_API_KEY")
        secret = os.getenv("ALPACA_SECRET_KEY")
        if not key or not secret:
            raise AlpacaUnavailable("Alpaca paper credentials are not configured")
        self._client = TradingClient(key, secret, paper=cfg.get("mode") != "live")
        self._request_cls = MarketOrderRequest
        self._side_cls = OrderSide
        self._tif_cls = TimeInForce

    def submit(self, order: Order) -> OrderResult:
        request = self._request_cls(
            symbol=order.ticker,
            qty=order.qty,
            side=self._side_cls.BUY if order.side == "buy" else self._side_cls.SELL,
            time_in_force=self._tif_cls.DAY,
            client_order_id=order.client_order_id,
        )
        result = self._client.submit_order(request)
        return OrderResult(order.client_order_id, order.ticker, order.side, order.qty, str(getattr(result, "status", "submitted")))

    def positions(self) -> list[BrokerPosition]:
        positions = []
        for pos in self._client.get_all_positions():
            positions.append(BrokerPosition(pos.symbol, float(pos.qty), float(pos.avg_entry_price), "stock"))
        return positions

    def reconcile(self, trade_log: list[dict]) -> dict:
        broker_symbols = {p.ticker for p in self.positions()}
        log_symbols = {row.get("ticker") for row in trade_log if row.get("status") in {"open", "accepted"} or row.get("side") == "buy"}
        return {
            "missing_in_broker": sorted(symbol for symbol in log_symbols - broker_symbols if symbol),
            "missing_in_log": sorted(broker_symbols - log_symbols),
            "broker_positions": sorted(broker_symbols),
        }
