from __future__ import annotations

import math


def compute_metrics(
    equity_curve: list[float],
    benchmark_curve: list[float] | None = None,
    trades: list[dict] | None = None,
    exposures: list[float] | None = None,
    periods_per_year: float = 252,
) -> dict:
    if not equity_curve:
        return {"total_return": 0.0, "cagr": 0.0, "sharpe": 0.0, "max_drawdown": 0.0, "hit_rate": 0.0, "vs_benchmark": 0.0}
    start = equity_curve[0]
    end = equity_curve[-1]
    returns = [(equity_curve[idx] - equity_curve[idx - 1]) / equity_curve[idx - 1] for idx in range(1, len(equity_curve)) if equity_curve[idx - 1]]
    peak = start
    max_dd = 0.0
    for value in equity_curve:
        peak = max(peak, value)
        if peak:
            max_dd = min(max_dd, (value - peak) / peak)
    benchmark_return = 0.0
    if benchmark_curve and benchmark_curve[0]:
        benchmark_return = (benchmark_curve[-1] - benchmark_curve[0]) / benchmark_curve[0]
    total = (end - start) / start if start else 0.0
    years = max(1 / periods_per_year, (len(equity_curve) - 1) / periods_per_year)
    cagr = (end / start) ** (1 / years) - 1 if start and end > 0 else 0.0
    sharpe = _sharpe(returns, periods_per_year)
    trades = trades or []
    hit_rate = sum(1 for trade in trades if trade.get("return_pct", 0.0) > 0) / len(trades) if trades else 0.0
    return {
        "total_return": round(total, 6),
        "cagr": round(cagr, 6),
        "sharpe": round(sharpe, 6),
        "max_drawdown": round(max_dd, 6),
        "hit_rate": round(hit_rate, 6),
        "vs_benchmark": round(total - benchmark_return, 6),
        "avg_exposure": round(sum(exposures or []) / len(exposures), 6) if exposures else 0.0,
        "trade_count": len(trades),
        "per_member": _attribution(trades, "member_id"),
        "per_sector": _attribution(trades, "sector"),
    }


def _sharpe(returns: list[float], periods_per_year: float) -> float:
    if len(returns) < 2:
        return 0.0
    mean = sum(returns) / len(returns)
    variance = sum((value - mean) ** 2 for value in returns) / (len(returns) - 1)
    stdev = math.sqrt(variance)
    return (mean / stdev) * math.sqrt(periods_per_year) if stdev else 0.0


def _attribution(trades: list[dict], key: str) -> dict[str, float]:
    out: dict[str, float] = {}
    for trade in trades:
        name = str(trade.get(key) or "unknown")
        out[name] = out.get(name, 0.0) + float(trade.get("pnl_pct", 0.0))
    return {name: round(value, 6) for name, value in sorted(out.items())}
