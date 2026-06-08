from __future__ import annotations

from datetime import date, datetime, timezone

from analytics.alpha_decay import freshness_score
from core.atr_sizing import calculate_position_qty
from core.models import MemberScore, Signal, Transaction
from core.risk_manager import portfolio_caps_allow
from engine.conviction import conviction_score
from engine.entry_quality import entry_quality_score

UTC = timezone.utc


def build_copy_signals(
    transactions: list[Transaction],
    member_scores: dict[str, MemberScore],
    cfg: dict,
    sector_map: dict[str, str],
    as_of: date,
    open_weights: dict[str, float] | None = None,
    member_exposures: dict[str, float] | None = None,
    market_prices: dict[str, float] | None = None,
    atr_by_ticker: dict[str, float] | None = None,
    liquidity: dict[str, dict[str, float]] | None = None,
    event_blackouts: dict[str, set[str]] | None = None,
    committee_relevance: set[tuple[str, str]] | None = None,
    stale_symbols: set[str] | None = None,
) -> list[Signal]:
    open_weights = dict(open_weights or {})
    member_exposures = dict(member_exposures or {})
    market_prices = market_prices or {}
    atr_by_ticker = atr_by_ticker or {}
    liquidity = liquidity or {}
    event_blackouts = event_blackouts or {}
    committee_relevance = committee_relevance or set()
    stale_symbols = stale_symbols or set()
    output: list[Signal] = []
    buys = [tx for tx in transactions if tx.tx_type == "buy" and tx.filing_date <= as_of]
    cluster_counts: dict[str, int] = {}
    for tx in buys:
        if tx.ticker:
            cluster_counts[tx.ticker] = cluster_counts.get(tx.ticker, 0) + 1
    for tx in buys:
        if not tx.ticker:
            output.append(_blocked(tx, "unresolved_ticker"))
            continue
        if tx.asset_type == "option" and not cfg.get("execution", {}).get("options_enabled", False):
            output.append(_blocked(tx, "options_disabled"))
            continue
        allowed_asset_types = set(cfg["signals"].get("allowed_asset_types", ["stock"]))
        if cfg.get("execution", {}).get("options_enabled", False):
            allowed_asset_types.add("option")
        if tx.asset_type not in allowed_asset_types:
            output.append(_blocked(tx, "asset_type_not_allowed"))
            continue
        if tx.ticker.upper() in stale_symbols:
            output.append(_blocked(tx, "stale_price"))
            continue
        liquid, liquidity_reason = _liquidity_ok(tx.ticker, liquidity, cfg)
        if not liquid:
            output.append(_blocked(tx, liquidity_reason or "liquidity_block"))
            continue
        fresh = freshness_score(tx.tx_date, as_of, cfg["exits"]["max_alpha_age_days"])
        if fresh < cfg["signals"]["min_freshness_score"]:
            output.append(_blocked(tx, "freshness_below_threshold", fresh))
            continue
        member_score = member_scores.get(tx.member_id)
        if not member_score or member_score.score < cfg["signals"]["min_member_score"]:
            output.append(_blocked(tx, "member_score_below_threshold", fresh))
            continue
        sector = sector_map.get(tx.ticker.upper(), "Unknown")
        committee_relevant = (tx.member_id, tx.ticker.upper()) in committee_relevance or (tx.member_id, sector) in committee_relevance
        conviction = conviction_score(tx, member_score, cluster_counts.get(tx.ticker, 1), committee_relevant)
        if conviction < cfg["signals"]["min_conviction_score"]:
            output.append(_blocked(tx, "conviction_below_threshold", fresh, conviction))
            continue
        events = event_blackouts.get(tx.ticker.upper(), set())
        entry_quality, blocked = entry_quality_score(
            tx,
            cfg,
            earnings_blackout="earnings" in events,
            corporate_action_blackout="corporate_action" in events,
        )
        if blocked:
            output.append(_blocked(tx, blocked, fresh, conviction, entry_quality))
            continue
        target_weight = _target_weight(tx, cfg, conviction, fresh, entry_quality, market_prices, atr_by_ticker)
        ok, reason = portfolio_caps_allow(tx.ticker, target_weight, open_weights, sector_map, cfg, tx.member_id, member_exposures)
        if not ok:
            output.append(_blocked(tx, reason or "risk_cap", fresh, conviction, entry_quality))
            continue
        open_weights[tx.ticker] = target_weight
        member_exposures[tx.member_id] = member_exposures.get(tx.member_id, 0.0) + target_weight
        output.append(
            Signal(
                signal_id=f"sig-{tx.tx_id}",
                created_at=datetime.now(UTC),
                ticker=tx.ticker,
                asset_type=tx.asset_type,
                side="copy_buy",
                source_tx_ids=[tx.tx_id],
                conviction_score=conviction,
                freshness_score=fresh,
                entry_quality_score=entry_quality,
                target_weight_pct=target_weight,
                rationale=f"copy buy from {tx.member_id}; conviction={conviction}; freshness={fresh}; quality={entry_quality}",
            )
        )
    return output


def _blocked(tx: Transaction, reason: str, fresh: float = 0.0, conviction: float = 0.0, quality: float = 0.0) -> Signal:
    return Signal(
        signal_id=f"blocked-{tx.tx_id}",
        created_at=datetime.now(UTC),
        ticker=tx.ticker or "UNRESOLVED",
        asset_type=tx.asset_type,
        side="copy_buy",
        source_tx_ids=[tx.tx_id],
        conviction_score=conviction,
        freshness_score=fresh,
        entry_quality_score=quality,
        target_weight_pct=0.0,
        rationale="candidate blocked",
        blocked_reason=reason,
    )


def _target_weight(
    tx: Transaction,
    cfg: dict,
    conviction: float,
    fresh: float,
    entry_quality: float,
    market_prices: dict[str, float],
    atr_by_ticker: dict[str, float],
) -> float:
    scale = max(0.0, min(1.0, conviction * fresh * entry_quality))
    price = market_prices.get(tx.ticker or "") or tx.price_on_filing_date or tx.price_on_tx_date
    atr = atr_by_ticker.get(tx.ticker or "")
    if price and atr:
        stop_price = max(0.01, price - (2 * atr))
        qty = calculate_position_qty(
            cfg["risk"]["account_equity"],
            cfg["risk"]["risk_per_trade_pct"],
            price,
            stop_price,
            cfg["risk"]["max_position_pct"],
            scale,
        )
        return round(min(cfg["risk"]["max_position_pct"], (qty * price) / cfg["risk"]["account_equity"]), 4)
    return round(min(cfg["risk"]["max_position_pct"], cfg["risk"]["max_position_pct"] * scale), 4)


def _liquidity_ok(ticker: str, liquidity: dict[str, dict[str, float]], cfg: dict) -> tuple[bool, str | None]:
    data = liquidity.get(ticker.upper())
    if not data:
        return True, None
    if data.get("adv_dollars", float("inf")) < cfg["signals"].get("min_adv_dollars", 0):
        return False, "low_liquidity"
    if data.get("spread_pct", 0.0) > cfg["signals"].get("max_spread_pct", 1.0):
        return False, "wide_spread"
    return True, None
