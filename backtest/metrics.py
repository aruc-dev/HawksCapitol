from __future__ import annotations


def compute_metrics(equity_curve: list[float], benchmark_curve: list[float] | None = None) -> dict[str, float]:
    if not equity_curve:
        return {"total_return": 0.0, "max_drawdown": 0.0, "vs_benchmark": 0.0}
    start = equity_curve[0]
    end = equity_curve[-1]
    peak = start
    max_dd = 0.0
    for value in equity_curve:
        peak = max(peak, value)
        if peak:
            max_dd = min(max_dd, (value - peak) / peak)
    benchmark_return = 0.0
    if benchmark_curve:
        benchmark_return = (benchmark_curve[-1] - benchmark_curve[0]) / benchmark_curve[0]
    total = (end - start) / start if start else 0.0
    return {
        "total_return": round(total, 6),
        "max_drawdown": round(max_dd, 6),
        "vs_benchmark": round(total - benchmark_return, 6),
    }
