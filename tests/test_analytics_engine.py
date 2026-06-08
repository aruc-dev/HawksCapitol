from __future__ import annotations

from datetime import date
import unittest

from analytics.alpha_decay import freshness_score
from analytics.member_score import compute_member_scores
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


if __name__ == "__main__":
    unittest.main()
