from __future__ import annotations

from core.models import Transaction


def entry_quality_score(
    tx: Transaction,
    cfg: dict,
    earnings_blackout: bool = False,
    corporate_action_blackout: bool = False,
    regime_ok: bool = True,
) -> tuple[float, str | None]:
    signals = cfg["signals"]
    if tx.ticker is None:
        return 0.0, "unresolved_ticker"
    if tx.source_quality != "official" and not cfg.get("allow_third_party_entries", False):
        return 0.0, "source_unverified"
    if tx.parse_confidence < 0.75:
        return 0.0, "low_parse_confidence"
    if tx.filing_lag_days > signals["max_filing_lag_days"]:
        return 0.0, "stale_filing"
    if tx.filing_gap_pct is not None and abs(tx.filing_gap_pct) > signals["max_filing_gap_pct"]:
        return 0.0, "large_filing_gap"
    if earnings_blackout:
        return 0.0, "earnings_blackout"
    if corporate_action_blackout:
        return 0.0, "corporate_action_blackout"
    if not regime_ok:
        return 0.0, "regime_block"
    lag_component = max(0.0, 1.0 - tx.filing_lag_days / signals["max_filing_lag_days"])
    gap_component = 1.0
    if tx.filing_gap_pct is not None:
        gap_component = max(0.0, 1.0 - abs(tx.filing_gap_pct) / signals["max_filing_gap_pct"])
    score = round((0.55 * lag_component) + (0.25 * gap_component) + (0.20 * tx.parse_confidence), 4)
    if score < signals["min_entry_quality_score"]:
        return score, "entry_quality_below_threshold"
    return score, None
