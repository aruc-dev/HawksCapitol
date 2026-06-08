from __future__ import annotations


def sector_exposure_ok(
    ticker: str,
    sector_map: dict[str, str],
    current_weights: dict[str, float],
    proposed_weight: float,
    max_sector_exposure_pct: float,
) -> bool:
    sector = sector_map.get(ticker.upper(), "Unknown")
    current = sum(weight for sym, weight in current_weights.items() if sector_map.get(sym.upper(), "Unknown") == sector)
    return current + proposed_weight <= max_sector_exposure_pct
