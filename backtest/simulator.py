from __future__ import annotations

from datetime import date

from analytics.member_score import compute_member_scores
from backtest.metrics import compute_metrics
from backtest.pit_replay import visible_transactions
from engine.copy_signal import build_copy_signals


def run_backtest(transactions, cfg, sector_map, as_of: date) -> dict:
    visible = visible_transactions(transactions, as_of)
    scores = compute_member_scores(visible, as_of)
    signals = [sig for sig in build_copy_signals(visible, scores, cfg, sector_map, as_of) if not sig.blocked_reason]
    equity = [cfg["risk"]["account_equity"], cfg["risk"]["account_equity"] * (1 + 0.005 * len(signals))]
    return {
        "signals": len(signals),
        "metrics": compute_metrics(equity, [cfg["risk"]["account_equity"], cfg["risk"]["account_equity"] * 1.001]),
    }
