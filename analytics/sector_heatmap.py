from __future__ import annotations

from datetime import date, timedelta

from core.models import Transaction
from core.price_history import window_return


def compute_sector_heatmap(
    transactions: list[Transaction],
    sector_map: dict[str, str],
    as_of: date,
    price_history: dict[str, dict[date, float]] | None = None,
    lookback_days: int = 30,
) -> dict[str, dict]:
    heat: dict[str, dict] = {}
    price_history = price_history or {}
    for tx in transactions:
        if tx.filing_date > as_of or tx.tx_type != "buy" or not tx.ticker:
            continue
        if (as_of - tx.filing_date).days > lookback_days:
            continue
        sector = sector_map.get(tx.ticker.upper(), "Unknown")
        row = heat.setdefault(sector, {"count": 0, "amount_mid": 0.0, "members": set(), "alpha_30_samples": []})
        row["count"] += 1
        row["amount_mid"] += tx.amount_mid
        row["members"].add(tx.member_id)
        alpha_30 = _alpha_30(tx, price_history, as_of)
        if alpha_30 is not None:
            row["alpha_30_samples"].append(alpha_30)
    output = {}
    for sector, row in heat.items():
        samples = row["alpha_30_samples"]
        output[sector] = {
            "count": row["count"],
            "amount_mid": row["amount_mid"],
            "active_members": sorted(row["members"]),
            "avg_alpha_30d": round(sum(samples) / len(samples), 6) if samples else 0.0,
            "sample_count": len(samples),
        }
    return output


def _alpha_30(tx: Transaction, price_history: dict[str, dict[date, float]], as_of: date) -> float | None:
    end_date = tx.tx_date + timedelta(days=30)
    if end_date > as_of:
        return None
    prices = price_history.get(tx.ticker.upper(), {})
    benchmark = price_history.get("SPY", {})
    symbol_return = window_return(prices, tx.tx_date, end_date)
    benchmark_return = window_return(benchmark, tx.tx_date, end_date)
    if symbol_return is None or benchmark_return is None:
        return None
    return symbol_return - benchmark_return
