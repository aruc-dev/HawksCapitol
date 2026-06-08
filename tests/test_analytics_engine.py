from __future__ import annotations

from datetime import date
import unittest

from analytics.alpha_decay import AlphaDecayCurve, compute_alpha_decay_curve, freshness_score
from analytics.member_score import compute_member_scores
from analytics.sector_heatmap import compute_sector_heatmap
from backtest.pit_replay import visible_transactions
from core.config_loader import load_config
from core.sample_data import sample_as_of, sample_sector_map, sample_transactions
from engine.copy_signal import build_copy_signals
from engine.entry_quality import entry_quality_score
from ingestion.normalizer import normalize_records


class AnalyticsEngineTests(unittest.TestCase):
    def test_freshness_decays_with_transaction_age(self) -> None:
        self.assertEqual(freshness_score(date(2026, 6, 1), date(2026, 6, 1), 60), 1.0)
        self.assertEqual(freshness_score(date(2026, 4, 1), date(2026, 6, 1), 60), 0.0)
        curve = AlphaDecayCurve({30: 0.05, 90: -0.01}, {30: 3, 90: 3})
        self.assertEqual(freshness_score(date(2026, 5, 2), date(2026, 6, 1), 60, curve), 0.0)

    def test_alpha_decay_curve_uses_only_closed_visible_episodes(self) -> None:
        _, txs = normalize_records([
            {
                "doc_id": "closed",
                "source": "house_clerk",
                "member_name": "Curve Member",
                "filing_date": "2026-01-02",
                "tx_date": "2026-01-01",
                "ticker": "AAPL",
                "asset_name": "Apple",
                "tx_type": "Purchase",
                "amount": "$1,001 - $15,000",
            },
            {
                "doc_id": "future-filed",
                "source": "house_clerk",
                "member_name": "Curve Member",
                "filing_date": "2026-04-01",
                "tx_date": "2026-01-01",
                "ticker": "MSFT",
                "asset_name": "Microsoft",
                "tx_type": "Purchase",
                "amount": "$1,001 - $15,000",
            },
        ])
        prices = {
            "AAPL": {date(2026, 1, 1): 100.0, date(2026, 1, 31): 110.0, date(2026, 4, 1): 120.0},
            "MSFT": {date(2026, 1, 1): 100.0, date(2026, 1, 31): 200.0},
            "SPY": {date(2026, 1, 1): 100.0, date(2026, 1, 31): 102.0, date(2026, 4, 1): 103.0},
        }
        curve = compute_alpha_decay_curve(txs, prices, date(2026, 2, 1), horizons=(30, 90))
        self.assertEqual(curve.samples[30], 1)
        self.assertEqual(curve.samples[90], 0)
        self.assertAlmostEqual(curve.horizon_alpha[30], 0.08)

    def test_member_score_uses_only_visible_filings_and_sparse_guard(self) -> None:
        _, txs = normalize_records([
            {
                "doc_id": "d1",
                "source": "house_clerk",
                "member_name": "Sparse Member",
                "filing_date": "2026-06-01",
                "tx_date": "2026-05-01",
                "ticker": "AAPL",
                "asset_name": "Apple",
                "tx_type": "Purchase",
                "amount": "$1,001 - $15,000",
                "source_quality": "official",
            },
            {
                "doc_id": "future",
                "source": "house_clerk",
                "member_name": "Sparse Member",
                "filing_date": "2026-12-01",
                "tx_date": "2026-05-01",
                "ticker": "MSFT",
                "asset_name": "Microsoft",
                "tx_type": "Purchase",
                "amount": "$1,000,001 - $5,000,000",
                "source_quality": "official",
            },
        ])
        visible = visible_transactions(txs, date(2026, 6, 2))
        scores = compute_member_scores(visible, date(2026, 6, 2))
        score = scores["sparse-member"]
        self.assertEqual(score.n_trades, 1)
        self.assertLessEqual(score.score, 0.49)

    def test_member_score_uses_closed_alpha_and_sector_concentration(self) -> None:
        _, txs = normalize_records([
            {
                "doc_id": "a",
                "source": "house_clerk",
                "member_name": "Alpha Member",
                "filing_date": "2026-01-02",
                "tx_date": "2026-01-01",
                "ticker": "AAPL",
                "asset_name": "Apple",
                "tx_type": "Purchase",
                "amount": "$1,001 - $15,000",
            },
            {
                "doc_id": "b",
                "source": "house_clerk",
                "member_name": "Alpha Member",
                "filing_date": "2026-01-03",
                "tx_date": "2026-01-01",
                "ticker": "MSFT",
                "asset_name": "Microsoft",
                "tx_type": "Purchase",
                "amount": "$1,001 - $15,000",
            },
            {
                "doc_id": "c",
                "source": "house_clerk",
                "member_name": "Alpha Member",
                "filing_date": "2026-01-04",
                "tx_date": "2026-01-01",
                "ticker": "XOM",
                "asset_name": "Exxon Mobil",
                "tx_type": "Purchase",
                "amount": "$1,001 - $15,000",
            },
        ])
        prices = {
            "AAPL": {date(2026, 1, 1): 100.0, date(2026, 1, 31): 112.0},
            "MSFT": {date(2026, 1, 1): 100.0, date(2026, 1, 31): 108.0},
            "XOM": {date(2026, 1, 1): 100.0, date(2026, 1, 31): 95.0},
            "SPY": {date(2026, 1, 1): 100.0, date(2026, 1, 31): 102.0},
        }
        sector_map = {"AAPL": "Technology", "MSFT": "Technology", "XOM": "Energy"}
        score = compute_member_scores(txs, date(2026, 2, 1), price_history=prices, sector_map=sector_map)["alpha-member"]
        self.assertEqual(score.n_trades, 3)
        self.assertAlmostEqual(score.hit_rate, 2 / 3, places=4)
        self.assertAlmostEqual(score.sector_concentration, 2 / 3, places=4)
        self.assertGreater(score.avg_alpha_30d, 0.0)

    def test_sector_heatmap_tracks_recent_flow_and_profitability(self) -> None:
        txs = sample_transactions()
        prices = {
            "AAPL": {date(2026, 5, 15): 100.0, date(2026, 6, 14): 110.0},
            "MSFT": {date(2026, 5, 20): 100.0, date(2026, 6, 19): 105.0},
            "NVDA": {date(2026, 5, 25): 100.0, date(2026, 6, 24): 120.0},
            "SPY": {
                date(2026, 5, 15): 100.0,
                date(2026, 6, 14): 101.0,
                date(2026, 5, 20): 100.0,
                date(2026, 6, 19): 101.0,
                date(2026, 5, 25): 100.0,
                date(2026, 6, 24): 101.0,
            },
        }
        heat = compute_sector_heatmap(txs, sample_sector_map(), date(2026, 6, 30), price_history=prices, lookback_days=45)
        self.assertEqual(heat["Technology"]["count"], 3)
        self.assertEqual(heat["Technology"]["sample_count"], 3)
        self.assertGreater(heat["Technology"]["avg_alpha_30d"], 0.0)

    def test_copy_signal_blocks_and_allows_candidates(self) -> None:
        cfg = load_config()
        txs = sample_transactions()
        scores = compute_member_scores(txs, sample_as_of())
        signals = build_copy_signals(txs, scores, cfg, sample_sector_map(), sample_as_of())
        allowed = [sig for sig in signals if not sig.blocked_reason]
        self.assertGreaterEqual(len(allowed), 1)
        self.assertTrue(all(sig.target_weight_pct > 0 for sig in allowed))

    def test_copy_signal_accumulates_sector_exposure_for_new_candidates(self) -> None:
        cfg = load_config()
        cfg = {**cfg, "risk": {**cfg["risk"], "max_sector_exposure_pct": 0.04}}
        txs = sample_transactions()
        scores = compute_member_scores(txs, sample_as_of())
        signals = build_copy_signals(txs, scores, cfg, sample_sector_map(), sample_as_of())
        allowed = [sig for sig in signals if not sig.blocked_reason]
        blocked = [sig for sig in signals if sig.blocked_reason == "max_sector_exposure"]
        self.assertEqual(len(allowed), 1)
        self.assertGreaterEqual(len(blocked), 1)

    def test_entry_quality_blocks_large_filing_gap(self) -> None:
        cfg = load_config()
        tx = sample_transactions()[0]
        bad = tx.__class__(**{**tx.__dict__, "filing_gap_pct": 0.50})
        score, reason = entry_quality_score(bad, cfg)
        self.assertEqual(score, 0.0)
        self.assertEqual(reason, "large_filing_gap")

    def test_copy_signal_blocks_liquidity_events_and_asset_types(self) -> None:
        cfg = load_config()
        txs = sample_transactions()
        scores = compute_member_scores(txs, sample_as_of())
        option_tx = txs[0].__class__(**{**txs[0].__dict__, "tx_id": "opt", "ticker": "AAPL240621C200", "asset_type": "option"})
        low_liq = build_copy_signals([txs[0]], scores, cfg, sample_sector_map(), sample_as_of(), liquidity={"AAPL": {"adv_dollars": -1}})
        wide = build_copy_signals([txs[0]], scores, cfg, sample_sector_map(), sample_as_of(), liquidity={"AAPL": {"spread_pct": 0.50}})
        event = build_copy_signals([txs[0]], scores, cfg, sample_sector_map(), sample_as_of(), event_blackouts={"AAPL": {"earnings"}})
        asset = build_copy_signals([option_tx], scores, cfg, sample_sector_map(), sample_as_of())
        self.assertEqual(low_liq[0].blocked_reason, "low_liquidity")
        self.assertEqual(wide[0].blocked_reason, "wide_spread")
        self.assertEqual(event[0].blocked_reason, "earnings_blackout")
        self.assertEqual(asset[0].blocked_reason, "options_disabled")

    def test_copy_signal_enforces_member_cap_and_uses_atr_sizing(self) -> None:
        cfg = load_config()
        cfg = {**cfg, "risk": {**cfg["risk"], "max_member_exposure_pct": 0.05}}
        txs = sample_transactions()
        scores = compute_member_scores(txs, sample_as_of())
        signals = build_copy_signals(
            txs,
            scores,
            cfg,
            sample_sector_map(),
            sample_as_of(),
            market_prices={"AAPL": 100.0, "MSFT": 100.0, "NVDA": 100.0},
            atr_by_ticker={"AAPL": 2.0, "MSFT": 2.0, "NVDA": 2.0},
        )
        allowed = [sig for sig in signals if not sig.blocked_reason]
        blocked = [sig for sig in signals if sig.blocked_reason == "max_member_exposure"]
        self.assertEqual(len(allowed), 1)
        self.assertGreaterEqual(len(blocked), 1)
        amount_mirrored_weight = txs[0].amount_mid / cfg["risk"]["account_equity"]
        self.assertNotAlmostEqual(allowed[0].target_weight_pct, amount_mirrored_weight)
        self.assertLessEqual(allowed[0].target_weight_pct, cfg["risk"]["max_position_pct"])


if __name__ == "__main__":
    unittest.main()
