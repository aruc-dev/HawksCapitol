from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from core.models import Transaction
from core.price_history import window_return


@dataclass(frozen=True)
class AlphaDecayCurve:
    horizon_alpha: dict[int, float]
    samples: dict[int, int]

    def max_positive_age_days(self, fallback: int = 60) -> int:
        positive = [horizon for horizon, alpha in self.horizon_alpha.items() if alpha > 0 and self.samples.get(horizon, 0) > 0]
        return max(positive) if positive else fallback


def freshness_score(
    tx_date: date,
    as_of: date,
    max_alpha_age_days: int = 60,
    curve: AlphaDecayCurve | None = None,
) -> float:
    if curve is not None:
        max_alpha_age_days = curve.max_positive_age_days(max_alpha_age_days)
    age = max(0, (as_of - tx_date).days)
    return round(max(0.0, 1.0 - age / max_alpha_age_days), 4)


def compute_alpha_decay_curve(
    transactions: list[Transaction],
    price_history: dict[str, dict[date, float]],
    as_of: date,
    benchmark_symbol: str = "SPY",
    horizons: tuple[int, ...] = (30, 90, 180),
) -> AlphaDecayCurve:
    totals = {horizon: 0.0 for horizon in horizons}
    samples = {horizon: 0 for horizon in horizons}
    benchmark_prices = price_history.get(benchmark_symbol, {})
    for tx in transactions:
        if tx.tx_type != "buy" or tx.filing_date > as_of or not tx.ticker:
            continue
        symbol_prices = price_history.get(tx.ticker.upper(), {})
        for horizon in horizons:
            end_date = tx.tx_date + timedelta(days=horizon)
            if end_date > as_of:
                continue
            symbol_return = window_return(symbol_prices, tx.tx_date, end_date)
            benchmark_return = window_return(benchmark_prices, tx.tx_date, end_date)
            if symbol_return is None or benchmark_return is None:
                continue
            alpha = symbol_return - benchmark_return
            totals[horizon] += alpha
            samples[horizon] += 1
    horizon_alpha = {
        horizon: round(totals[horizon] / samples[horizon], 6) if samples[horizon] else 0.0
        for horizon in horizons
    }
    return AlphaDecayCurve(horizon_alpha, samples)
