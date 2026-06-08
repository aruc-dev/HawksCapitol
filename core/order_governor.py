from __future__ import annotations

from dataclasses import dataclass

from core.models import Order


@dataclass
class OrderGovernor:
    max_daily_orders: int
    max_notional: float
    submitted_count: int = 0

    def check(self, order: Order, price: float) -> None:
        if self.submitted_count >= self.max_daily_orders:
            raise ValueError("daily order limit reached")
        if abs(order.qty * price) > self.max_notional:
            raise ValueError("order notional exceeds governor limit")

    def record(self) -> None:
        self.submitted_count += 1
