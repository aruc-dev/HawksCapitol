from __future__ import annotations

from core.correlation_guard import sector_exposure_ok


def portfolio_caps_allow(
    ticker: str,
    proposed_weight: float,
    open_positions: dict[str, float],
    sector_map: dict[str, str],
    cfg: dict,
    member_id: str | None = None,
    member_exposures: dict[str, float] | None = None,
) -> tuple[bool, str | None]:
    risk = cfg["risk"]
    member_exposures = member_exposures or {}
    if ticker in open_positions:
        return False, "already_open"
    if len(open_positions) >= risk["max_positions"]:
        return False, "max_positions"
    if proposed_weight > risk["max_position_pct"]:
        return False, "max_position_pct"
    if member_id and member_exposures.get(member_id, 0.0) + proposed_weight > risk.get("max_member_exposure_pct", 1.0):
        return False, "max_member_exposure"
    if not sector_exposure_ok(ticker, sector_map, open_positions, proposed_weight, risk["max_sector_exposure_pct"]):
        return False, "max_sector_exposure"
    return True, None
