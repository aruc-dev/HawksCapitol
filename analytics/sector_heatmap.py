from __future__ import annotations

from datetime import date, timedelta

from core.models import Transaction


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
    start = prices.get(tx.tx_date)
    end = prices.get(end_date)
    bench_start = benchmark.get(tx.tx_date)
    bench_end = benchmark.get(end_date)
    if not start or not end or not bench_start or not bench_end:
        return None
    return ((end - start) / start) - ((bench_end - bench_start) / bench_start)
