from __future__ import annotations

from datetime import date

from core.models import Transaction


def compute_sector_heatmap(transactions: list[Transaction], sector_map: dict[str, str], as_of: date) -> dict[str, dict[str, float]]:
    heat: dict[str, dict[str, float]] = {}
    for tx in transactions:
        if tx.filing_date > as_of or tx.tx_type != "buy" or not tx.ticker:
            continue
        sector = sector_map.get(tx.ticker.upper(), "Unknown")
        row = heat.setdefault(sector, {"count": 0, "amount_mid": 0.0})
        row["count"] += 1
        row["amount_mid"] += tx.amount_mid
    return heat
