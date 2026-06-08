from __future__ import annotations

from datetime import date, timedelta

from core.models import MemberScore, Transaction


def compute_member_scores(
    transactions: list[Transaction],
    as_of: date,
    min_sample: int = 3,
    price_history: dict[str, dict[date, float]] | None = None,
    sector_map: dict[str, str] | None = None,
    benchmark_symbol: str = "SPY",
) -> dict[str, MemberScore]:
    visible = [tx for tx in transactions if tx.filing_date <= as_of and tx.tx_type == "buy"]
    by_member: dict[str, list[Transaction]] = {}
    for tx in visible:
        by_member.setdefault(tx.member_id, []).append(tx)
    scores: dict[str, MemberScore] = {}
    for member_id, rows in by_member.items():
        n = len(rows)
        avg_lag = sum(tx.filing_lag_days for tx in rows) / n
        sample_quality = min(1.0, n / min_sample)
        latency_score = max(0.0, 1.0 - avg_lag / 60)
        amount_score = min(1.0, sum(tx.amount_mid for tx in rows) / max(1.0, n * 50000))
        parse_score = sum(tx.parse_confidence for tx in rows) / n
        alpha_30 = _closed_alpha(rows, price_history or {}, as_of, 30, benchmark_symbol)
        alpha_90 = _closed_alpha(rows, price_history or {}, as_of, 90, benchmark_symbol)
        closed_30 = [value for value in alpha_30 if value is not None]
        closed_90 = [value for value in alpha_90 if value is not None]
        hit_rate = sum(1 for value in closed_30 if value > 0) / len(closed_30) if closed_30 else 0.5
        avg_alpha_30 = sum(closed_30) / len(closed_30) if closed_30 else 0.0
        avg_alpha_90 = sum(closed_90) / len(closed_90) if closed_90 else 0.0
        alpha_score = _clamp(0.5 + avg_alpha_30 * 5, 0.0, 1.0)
        concentration = _sector_concentration(rows, sector_map or {})
        diversification_score = 1.0 - concentration if sector_map else 0.5
        score = round(
            (0.25 * sample_quality)
            + (0.20 * hit_rate)
            + (0.20 * alpha_score)
            + (0.15 * latency_score)
            + (0.10 * amount_score)
            + (0.07 * parse_score)
            + (0.03 * diversification_score),
            4,
        )
        if n < min_sample:
            score = min(score, 0.49)
        scores[member_id] = MemberScore(
            member_id=member_id,
            as_of_date=as_of,
            n_trades=n,
            hit_rate=round(hit_rate, 4),
            avg_alpha_30d=round(avg_alpha_30, 6),
            avg_alpha_90d=round(avg_alpha_90, 6),
            median_hold=0,
            filing_latency_days=round(avg_lag, 2),
            sector_concentration=round(concentration, 4),
            sample_quality=round(sample_quality, 4),
            score=score,
        )
    return scores


def _closed_alpha(
    rows: list[Transaction],
    price_history: dict[str, dict[date, float]],
    as_of: date,
    horizon_days: int,
    benchmark_symbol: str,
) -> list[float | None]:
    benchmark_prices = price_history.get(benchmark_symbol, {})
    values: list[float | None] = []
    for tx in rows:
        if not tx.ticker:
            values.append(None)
            continue
        end_date = tx.tx_date + timedelta(days=horizon_days)
        if end_date > as_of:
            values.append(None)
            continue
        symbol_prices = price_history.get(tx.ticker.upper(), {})
        start = symbol_prices.get(tx.tx_date)
        end = symbol_prices.get(end_date)
        bench_start = benchmark_prices.get(tx.tx_date)
        bench_end = benchmark_prices.get(end_date)
        if not start or not end or not bench_start or not bench_end:
            values.append(None)
            continue
        values.append(((end - start) / start) - ((bench_end - bench_start) / bench_start))
    return values


def _sector_concentration(rows: list[Transaction], sector_map: dict[str, str]) -> float:
    if not rows or not sector_map:
        return 0.0
    counts: dict[str, int] = {}
    for tx in rows:
        sector = sector_map.get((tx.ticker or "").upper(), "Unknown")
        counts[sector] = counts.get(sector, 0) + 1
    return max(counts.values()) / len(rows)


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))
