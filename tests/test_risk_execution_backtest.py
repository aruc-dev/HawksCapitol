from __future__ import annotations

from datetime import date
from pathlib import Path
import tempfile
import unittest

from backtest.metrics import compute_metrics
from backtest.simulator import run_backtest
from analytics.member_score import compute_member_scores
from broker.paper_broker import PaperBroker
from core.config_loader import load_config
from core.live_mode_guard import LiveModeBlocked, assert_live_allowed
from core.live_promotion import PromotionEvidence, evaluate_live_promotion
from core.models import MarketSnapshot, Order, Position
from core.broker_stops import sync_protective_stops
from core.order_executor import execute_signal
from core.order_governor import OrderGovernor
from core.sample_data import sample_as_of, sample_sector_map, sample_transactions
from ingestion.storage import read_json, write_json
from scheduler import reconcile_trade_log, run_backtest as run_backtest_scheduler, run_scan
from engine.copy_signal import build_copy_signals
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

        stale_exit = evaluate_positions(
            [pos],
            {"t1": date(2026, 5, 1)},
            MarketSnapshot(sample_as_of(), {}, stale_symbols={"AAPL"}, last_prices={"AAPL": 90}),
            cfg,
        )
        self.assertEqual(stale_exit[0].reason, "hard_stop_loss")

    def test_sell_engine_each_exit_rule_and_priority_order(self) -> None:
        cfg = load_config()
        as_of = sample_as_of()
        base = Position("base", "AAPL", "stock", date(2026, 6, 1), 100, 1, 92, 120, 100)
        cases = [
            (base, MarketSnapshot(as_of, {"AAPL": 90}), date(2026, 5, 30), {}, "hard_stop_loss", 1),
            (base, MarketSnapshot(as_of, {"AAPL": 121}), date(2026, 5, 30), {}, "profit_target", 2),
            (Position("trail", "AAPL", "stock", date(2026, 6, 1), 100, 1, 92, 150, 130), MarketSnapshot(as_of, {"AAPL": 119}), date(2026, 5, 30), {}, "trailing_stop", 3),
            (base, MarketSnapshot(as_of, {"AAPL": 100}), date(2026, 3, 1), {}, "alpha_decay_time_stop", 4),
            (base, MarketSnapshot(as_of, {"AAPL": 100}, events={"AAPL": {"member_sell"}}), date(2026, 5, 30), {}, "member_sell_filed", 5),
            (base, MarketSnapshot(as_of, {"AAPL": 100}, regime_ok=False), date(2026, 5, 30), {}, "regime_exit", 5),
            (base, MarketSnapshot(as_of, {"AAPL": 100}, events={"AAPL": {"earnings"}}), date(2026, 5, 30), {}, "earnings_blackout_exit", 5),
            (base, MarketSnapshot(as_of, {"AAPL": 100}), date(2026, 5, 30), {"demo": 0.1}, "conviction_decay", 6),
            (Position("hold", "AAPL", "stock", date(2026, 1, 1), 100, 1, 92, 150, 100), MarketSnapshot(as_of, {"AAPL": 100}), date(2026, 5, 30), {}, "max_hold_cap", 7),
        ]
        for pos, market, tx_date, member_scores, reason, priority in cases:
            pos.member_ids = ["demo"]
            decisions = evaluate_positions([pos], {pos.trade_id: tx_date}, market, cfg, member_scores)
            self.assertEqual((decisions[0].reason, decisions[0].priority), (reason, priority))

        priority = evaluate_positions(
            [base],
            {"base": date(2026, 3, 1)},
            MarketSnapshot(as_of, {"AAPL": 90}, events={"AAPL": {"member_sell"}}),
            cfg,
        )
        self.assertEqual(priority[0].reason, "hard_stop_loss")

    def test_stale_symbols_block_entries(self) -> None:
        cfg = load_config()
        txs = sample_transactions()
        scores = compute_member_scores(txs, sample_as_of())
        signals = build_copy_signals(txs[:1], scores, cfg, sample_sector_map(), sample_as_of(), stale_symbols={"AAPL"})
        self.assertEqual(signals[0].blocked_reason, "stale_price")

    def test_long_options_are_gated_and_can_be_paper_ordered_when_enabled(self) -> None:
        cfg = load_config()
        tx = sample_transactions()[0]
        option_tx = tx.__class__(
            **{
                **tx.__dict__,
                "tx_id": "option-1",
                "ticker": "AAPL240621C200",
                "asset_type": "option",
                "option_meta": {"right": "call", "strike": 200.0, "expiry": "2026-06-21"},
            }
        )
        scores = compute_member_scores(sample_transactions(), sample_as_of())
        disabled = build_copy_signals([option_tx], scores, cfg, sample_sector_map(), sample_as_of())
        self.assertEqual(disabled[0].blocked_reason, "options_disabled")
        enabled_cfg = {**cfg, "execution": {**cfg["execution"], "options_enabled": True}}
        enabled = build_copy_signals([option_tx], scores, enabled_cfg, sample_sector_map(), sample_as_of())
        self.assertIsNone(enabled[0].blocked_reason)
        blocked_order = execute_signal(enabled[0], PaperBroker(), cfg, price=2.5, governor=OrderGovernor(10, 100000))
        self.assertEqual(blocked_order.message, "options_disabled")
        accepted = execute_signal(enabled[0], PaperBroker(), enabled_cfg, price=2.5, governor=OrderGovernor(10, 100000))
        self.assertEqual(accepted.status, "accepted")

    def test_option_specific_exits(self) -> None:
        cfg = load_config()
        as_of = sample_as_of()
        near_expiry = Position(
            "opt-time",
            "AAPL240621C200",
            "option",
            date(2026, 6, 1),
            2.0,
            1,
            1.0,
            4.0,
            2.0,
            option_meta={"right": "call", "strike": 200.0, "expiry": "2026-06-10"},
        )
        profit = Position("opt-profit", "AAPL240821C200", "option", date(2026, 6, 1), 2.0, 1, 1.0, 10.0, 2.0, option_meta={"right": "call", "strike": 200.0, "expiry": "2026-08-21"})
        delta = Position("opt-delta", "AAPL240821C210", "option", date(2026, 6, 1), 2.0, 1, 1.0, 10.0, 2.0, option_meta={"right": "call", "strike": 210.0, "expiry": "2026-08-21"})
        self.assertEqual(evaluate_positions([near_expiry], {"opt-time": date(2026, 6, 1)}, MarketSnapshot(as_of, {"AAPL240621C200": 2.1}), cfg)[0].reason, "option_time_to_expiry")
        self.assertEqual(evaluate_positions([profit], {"opt-profit": date(2026, 6, 1)}, MarketSnapshot(as_of, {"AAPL240821C200": 3.2}), cfg)[0].reason, "option_profit_target")
        self.assertEqual(
            evaluate_positions([delta], {"opt-delta": date(2026, 6, 1)}, MarketSnapshot(as_of, {"AAPL240821C210": 2.1}, option_metrics={"AAPL240821C210": {"delta": 0.05}}), cfg)[0].reason,
            "option_delta_decay",
        )

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

    def test_paper_broker_persists_and_scan_retries_do_not_duplicate(self) -> None:
        original_scan_load_config = run_scan.load_config
        try:
            with tempfile.TemporaryDirectory() as tmp:
                cfg = load_config()
                cfg["data_dir"] = str(Path(tmp) / "runtime-data")
                run_scan.load_config = lambda: cfg
                write_json(Path(cfg["data_dir"]) / "canonical" / "transactions.json", sample_transactions())

                state_path = Path(tmp) / "paper_state.json"
                trade_log_path = Path(tmp) / "trade_log.json"
                signals_path = Path(tmp) / "signals.json"
                broker = PaperBroker(state_path)
                order = Order("same", "AAPL", "buy", 10, limit_price=50.0)
                broker.submit(order)
                self.assertEqual(PaperBroker(state_path).submit(order).client_order_id, "same")
                self.assertEqual(len(read_json(state_path)["orders"]), 1)

                first = run_scan.run(
                    dry_run=False,
                    broker_state_path=state_path,
                    trade_log_path=trade_log_path,
                    signals_path=signals_path,
                    as_of=sample_as_of(),
                )
                second = run_scan.run(
                    dry_run=False,
                    broker_state_path=state_path,
                    trade_log_path=trade_log_path,
                    signals_path=signals_path,
                    as_of=sample_as_of(),
                )
                state = read_json(state_path)
                self.assertEqual(len({row["client_order_id"] for row in state["orders"]}), len(state["orders"]))
                self.assertEqual(len(first["accepted_orders"]), len(second["accepted_orders"]))
                self.assertTrue(read_json(signals_path))
                reconciliation = reconcile_trade_log.run(dry_run=True, broker_state_path=state_path, trade_log_path=trade_log_path)
                self.assertEqual(reconciliation["missing_in_broker"], [])
        finally:
            run_scan.load_config = original_scan_load_config

    def test_non_dry_scan_uses_canonical_transactions_without_sample_fallback(self) -> None:
        original_scan_load_config = run_scan.load_config
        try:
            with tempfile.TemporaryDirectory() as tmp:
                cfg = load_config()
                cfg["data_dir"] = str(Path(tmp) / "runtime-data")
                run_scan.load_config = lambda: cfg
                tx = sample_transactions()[0]
                canonical_only = tx.__class__(
                    **{
                        **tx.__dict__,
                        "tx_id": "canonical-only",
                        "doc_id": "canonical-doc",
                        "ticker": "XOM",
                        "asset_name_raw": "Exxon Mobil Corp",
                    }
                )
                write_json(Path(cfg["data_dir"]) / "canonical" / "transactions.json", [canonical_only])

                result = run_scan.run(dry_run=False, as_of=sample_as_of())

                self.assertEqual(len(result["signals"]), 1)
                self.assertEqual(result["signals"][0]["source_tx_ids"], ["canonical-only"])
                self.assertEqual(result["accepted_orders"], [])
        finally:
            run_scan.load_config = original_scan_load_config

    def test_non_dry_scan_missing_canonical_data_fails_closed(self) -> None:
        original_scan_load_config = run_scan.load_config
        try:
            with tempfile.TemporaryDirectory() as tmp:
                cfg = load_config()
                cfg["data_dir"] = str(Path(tmp) / "runtime-data")
                run_scan.load_config = lambda: cfg
                data_dir = Path(cfg["data_dir"])

                result = run_scan.run(dry_run=False, as_of=sample_as_of())

                self.assertEqual(result["signals"], [])
                self.assertEqual(result["accepted_orders"], [])
                self.assertEqual(read_json(data_dir / "signals" / "latest.json"), [])
                self.assertEqual(read_json(data_dir / "trade_log.json"), [])
                self.assertFalse((data_dir / "paper_broker" / "state.json").exists())
        finally:
            run_scan.load_config = original_scan_load_config

    def test_scan_and_reconcile_use_configured_data_dir_by_default(self) -> None:
        original_scan_load_config = run_scan.load_config
        original_reconcile_load_config = reconcile_trade_log.load_config
        try:
            with tempfile.TemporaryDirectory() as tmp:
                cfg = original_scan_load_config()
                cfg["data_dir"] = str(Path(tmp) / "custom-data")
                run_scan.load_config = lambda: cfg
                reconcile_trade_log.load_config = lambda: cfg
                write_json(Path(cfg["data_dir"]) / "canonical" / "transactions.json", sample_transactions())

                run_scan.run(dry_run=False, as_of=sample_as_of())
                reconciliation = reconcile_trade_log.run(dry_run=True)

                data_dir = Path(cfg["data_dir"])
                self.assertTrue((data_dir / "paper_broker" / "state.json").exists())
                self.assertTrue((data_dir / "signals" / "latest.json").exists())
                self.assertTrue((data_dir / "trade_log.json").exists())
                self.assertEqual(reconciliation["missing_in_broker"], [])
        finally:
            run_scan.load_config = original_scan_load_config
            reconcile_trade_log.load_config = original_reconcile_load_config

    def test_protective_stop_plans_are_deterministic(self) -> None:
        pos = Position("trade-1", "AAPL", "stock", date(2026, 6, 1), 100, 5, 92, 120, 100)
        stops = sync_protective_stops([pos])
        self.assertEqual(stops[0]["client_order_id"], "hc-stop-trade-1-AAPL")
        self.assertEqual(stops[0]["stop_price"], 92)

    def test_live_mode_guard_blocks_without_human_approval(self) -> None:
        cfg = load_config()
        live_cfg = {**cfg, "mode": "live", "execution": {**cfg["execution"], "allow_live": True}}
        with self.assertRaises(LiveModeBlocked):
            assert_live_allowed(live_cfg, human_approved=False)
        with self.assertRaises(LiveModeBlocked):
            assert_live_allowed({**cfg, "mode": "live"}, human_approved=True)

    def test_live_promotion_gate_requires_paper_evidence_and_human_approval(self) -> None:
        cfg = load_config()
        base = PromotionEvidence(
            backtest_verdict="watch",
            paper_weeks=2,
            paper_trades=4,
            paper_hit_rate=0.60,
            paper_max_drawdown_pct=0.02,
            origin_remote=cfg["promotion"]["expected_origin"],
            branch="main",
            human_approved=False,
        )
        blocked = evaluate_live_promotion(cfg, base)
        self.assertFalse(blocked["eligible"])
        self.assertIn("backtest_verdict_not_passed", blocked["reasons"])
        self.assertIn("insufficient_paper_weeks", blocked["reasons"])
        self.assertIn("explicit_human_live_approval_missing", blocked["reasons"])

        approved = evaluate_live_promotion(
            cfg,
            PromotionEvidence(
                backtest_verdict="pass",
                paper_weeks=4,
                paper_trades=20,
                paper_hit_rate=0.55,
                paper_max_drawdown_pct=0.04,
                origin_remote=cfg["promotion"]["expected_origin"],
                branch="main",
                human_approved=True,
            ),
        )
        self.assertTrue(approved["eligible"])
        self.assertEqual(approved["next_step"], "manual_live_change_review")

        wrong_ref = evaluate_live_promotion(
            cfg,
            PromotionEvidence(
                backtest_verdict="pass",
                paper_weeks=4,
                paper_trades=20,
                paper_hit_rate=0.55,
                paper_max_drawdown_pct=0.04,
                origin_remote="https://example.invalid/HawksCapitol.git",
                branch="feature",
                human_approved=True,
            ),
        )
        self.assertIn("deployment_branch_not_main", wrong_ref["reasons"])
        self.assertIn("deployment_origin_mismatch", wrong_ref["reasons"])

    def test_backtest_runs_and_returns_metrics(self) -> None:
        cfg = load_config()
        result = run_backtest(sample_transactions(), cfg, sample_sector_map(), sample_as_of())
        self.assertIn("metrics", result)
        self.assertGreaterEqual(result["signals"], 1)
        for key in ("cagr", "sharpe", "max_drawdown", "hit_rate", "vs_benchmark", "avg_exposure", "per_member", "per_sector"):
            self.assertIn(key, result["metrics"])
        self.assertIn(result["validation"]["verdict"], {"pass", "watch", "fail"})
        self.assertIn("spy", result["baselines"])

    def test_cagr_uses_return_period_count(self) -> None:
        metrics = compute_metrics([100.0, 110.0], periods_per_year=252)
        self.assertEqual(metrics["cagr"], round((1.10 ** 252) - 1, 6))

    def test_backtest_lookahead_guard_and_reproducibility(self) -> None:
        cfg = load_config()
        txs = sample_transactions()
        future = txs[0].__class__(
            **{
                **txs[0].__dict__,
                "tx_id": "future-big",
                "doc_id": "future-big",
                "filing_date": date(2026, 12, 1),
                "amount_min": 1_000_000.0,
                "amount_max": 5_000_000.0,
                "amount_mid": 3_000_000.0,
            }
        )
        baseline = run_backtest(txs, cfg, sample_sector_map(), sample_as_of(), days=1095)
        with_future = run_backtest(txs + [future], cfg, sample_sector_map(), sample_as_of(), days=1095)
        self.assertEqual(baseline["signals"], with_future["signals"])
        self.assertEqual(baseline["metrics"], with_future["metrics"])
        self.assertEqual(run_backtest_scheduler.run(dry_run=True, days=1095)["days"], 1095)


if __name__ == "__main__":
    unittest.main()
