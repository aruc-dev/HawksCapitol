from __future__ import annotations

from datetime import date
import unittest

from backtest.simulator import run_backtest
from broker.paper_broker import PaperBroker
from core.config_loader import load_config
from core.live_mode_guard import LiveModeBlocked, assert_live_allowed
from core.models import MarketSnapshot, Order, Position
from core.order_governor import OrderGovernor
from core.sample_data import sample_as_of, sample_sector_map, sample_transactions
from engine.sell_engine import evaluate_positions


class RiskExecutionBacktestTests(unittest.TestCase):
    def test_sell_engine_profit_target_and_alpha_decay(self) -> None:
        cfg = load_config()
        pos = Position("t1", "AAPL", "stock", date(2026, 6, 1), 100, 1, 92, 120, 100)
        decisions = evaluate_positions([pos], {"t1": date(2026, 5, 1)}, MarketSnapshot(sample_as_of(), {"AAPL": 121}), cfg)
        self.assertEqual(decisions[0].reason, "profit_target")

        pos2 = Position("t2", "MSFT", "stock", date(2026, 6, 1), 100, 1, 92, 150, 100)
        decisions2 = evaluate_positions([pos2], {"t2": date(2026, 3, 1)}, MarketSnapshot(sample_as_of(), {"MSFT": 101}), cfg)
        self.assertEqual(decisions2[0].reason, "alpha_decay_time_stop")

    def test_stale_price_alerts_without_silent_hold(self) -> None:
        cfg = load_config()
        pos = Position("t1", "AAPL", "stock", date(2026, 6, 1), 100, 1, 92, 120, 100)
        decisions = evaluate_positions([pos], {"t1": date(2026, 5, 1)}, MarketSnapshot(sample_as_of(), {}), cfg)
        self.assertEqual(decisions[0].action, "alert")

    def test_paper_broker_idempotency_and_governor(self) -> None:
        broker = PaperBroker()
        order = Order("same", "AAPL", "buy", 10, limit_price=50.0)
        first = broker.submit(order)
        second = broker.submit(order)
        self.assertEqual(first, second)
        self.assertEqual(len(broker.orders), 1)
        self.assertEqual(broker.positions()[0].avg_entry_price, 50.0)

        governor = OrderGovernor(max_daily_orders=1, max_notional=1000)
        governor.check(order, 50)
        governor.record()
        with self.assertRaises(ValueError):
            governor.check(Order("next", "MSFT", "buy", 1), 10)

    def test_live_mode_guard_blocks_without_human_approval(self) -> None:
        cfg = load_config()
        live_cfg = {**cfg, "mode": "live", "execution": {**cfg["execution"], "allow_live": True}}
        with self.assertRaises(LiveModeBlocked):
            assert_live_allowed(live_cfg, human_approved=False)

    def test_backtest_runs_and_returns_metrics(self) -> None:
        cfg = load_config()
        result = run_backtest(sample_transactions(), cfg, sample_sector_map(), sample_as_of())
        self.assertIn("metrics", result)
        self.assertGreaterEqual(result["signals"], 1)


if __name__ == "__main__":
    unittest.main()
