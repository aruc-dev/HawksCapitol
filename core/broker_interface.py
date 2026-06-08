from __future__ import annotations

from typing import Protocol

from core.models import BrokerPosition, Order, OrderResult


class Broker(Protocol):
    def submit(self, order: Order) -> OrderResult: ...
    def positions(self) -> list[BrokerPosition]: ...
    def reconcile(self, trade_log: list[dict]) -> dict: ...
