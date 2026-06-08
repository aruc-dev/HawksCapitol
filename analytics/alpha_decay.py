from __future__ import annotations

from datetime import date


def freshness_score(tx_date: date, as_of: date, max_alpha_age_days: int = 60) -> float:
    age = max(0, (as_of - tx_date).days)
    return round(max(0.0, 1.0 - age / max_alpha_age_days), 4)
