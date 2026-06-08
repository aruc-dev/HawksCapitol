from __future__ import annotations

from datetime import date, timedelta

from analytics.member_score import compute_member_scores
from backtest.metrics import compute_metrics
from backtest.pit_replay import visible_transactions
from core.price_history import window_return
from engine.copy_signal import build_copy_signals


def run_backtest(
    transactions,
    cfg,
    sector_map,
    as_of: date,
    days: int = 365,
    price_history: dict[str, dict[date, float]] | None = None,
) -> dict:
    start_date = as_of - timedelta(days=days)
    eligible_dates = sorted({tx.filing_date for tx in transactions if start_date <= tx.filing_date <= as_of})
    if not eligible_dates:
        eligible_dates = [as_of]
    equity = [cfg["risk"]["account_equity"]]
    benchmark = [cfg["risk"]["account_equity"]]
    exposures = []
    trades = []
    seen_signals: set[str] = set()
    price_history = price_history or {}
    price_history_supplied = bool(price_history)
    missing_price_returns = 0
    periods_per_year = _effective_periods_per_year(eligible_dates)
    for current in eligible_dates:
        visible = visible_transactions(transactions, current)
        in_window = [tx for tx in visible if start_date <= tx.filing_date <= current]
        scores = compute_member_scores(visible, current, price_history=price_history, sector_map=sector_map)
        signals = [sig for sig in build_copy_signals(in_window, scores, cfg, sector_map, current) if not sig.blocked_reason]
        day_pnl = 0.0
        day_exposure = 0.0
        for signal in signals:
            if signal.signal_id in seen_signals:
                continue
            tx = _tx_for_signal(visible, signal.source_tx_ids[0])
            if tx is None:
                continue
            return_pct = _estimate_return(tx, price_history, current, as_of, allow_fallback=not price_history_supplied)
            seen_signals.add(signal.signal_id)
            if return_pct is None:
                missing_price_returns += 1
                continue
            pnl_pct = signal.target_weight_pct * return_pct
            day_pnl += equity[-1] * pnl_pct
            day_exposure += signal.target_weight_pct
            trades.append(
                {
                    "signal_id": signal.signal_id,
                    "ticker": signal.ticker,
                    "member_id": tx.member_id,
                    "sector": sector_map.get(signal.ticker, "Unknown"),
                    "filing_date": tx.filing_date.isoformat(),
                    "target_weight_pct": signal.target_weight_pct,
                    "return_pct": round(return_pct, 6),
                    "pnl_pct": round(pnl_pct, 6),
                }
            )
        equity.append(max(0.0, equity[-1] + day_pnl))
        exposures.append(day_exposure)
        benchmark_return = _benchmark_return(price_history, current, as_of, allow_fallback=not price_history_supplied)
        benchmark.append(benchmark[-1] * (1 + (benchmark_return or 0.0)))
    metrics = compute_metrics(equity, benchmark, trades, exposures, periods_per_year=periods_per_year)
    baselines = _baselines(transactions, cfg, as_of, start_date, price_history)
    metrics["vs_benchmark"] = round(metrics["total_return"] - baselines["spy"]["total_return"], 6)
    validation = validate_backtest(metrics, baselines)
    return {
        "signals": len(trades),
        "metrics": metrics,
        "baselines": baselines,
        "validation": validation,
        "trades": trades,
        "equity_curve": [round(value, 2) for value in equity],
        "market_data": {
            "price_history_supplied": price_history_supplied,
            "return_model": "price_history_30d_returns" if price_history_supplied else "simulator_fallback_returns",
            "missing_price_returns": missing_price_returns,
            "periods_per_year": round(periods_per_year, 6),
        },
        "walk_forward": {
            "train_fraction": 0.7,
            "validation_fraction": 0.3,
            "note": "Promotion decisions must be based on out-of-sample paper results, not in-sample fit.",
        },
    }


def validate_backtest(metrics: dict, baselines: dict) -> dict:
    if metrics["trade_count"] < 3:
        verdict = "watch"
        reason = "sample size below promotion threshold"
    elif metrics["max_drawdown"] < -0.20:
        verdict = "fail"
        reason = "drawdown exceeds ceiling"
    elif metrics.get("vs_benchmark", 0.0) <= 0:
        verdict = "watch"
        reason = "strategy has not beaten benchmark curve"
    elif metrics["total_return"] <= baselines["spy"]["total_return"]:
        verdict = "watch"
        reason = "strategy has not beaten SPY baseline"
    else:
        verdict = "pass"
        reason = "sample, drawdown, and benchmark checks passed"
    return {"verdict": verdict, "reason": reason}


def _effective_periods_per_year(eligible_dates: list[date]) -> float:
    if len(eligible_dates) < 2:
        return 252.0
    elapsed_days = (eligible_dates[-1] - eligible_dates[0]).days
    if elapsed_days <= 0:
        return 252.0
    return max(1.0, len(eligible_dates) / (elapsed_days / 365.25))


def _tx_for_signal(transactions, tx_id: str):
    for tx in transactions:
        if tx.tx_id == tx_id:
            return tx
    return None


def _estimate_return(
    tx,
    price_history: dict[str, dict[date, float]],
    current: date,
    as_of: date,
    allow_fallback: bool = True,
) -> float | None:
    prices = price_history.get((tx.ticker or "").upper(), {})
    end_date = min(as_of, current + timedelta(days=30))
    realized = window_return(prices, current, end_date)
    if realized is not None:
        return realized
    if not allow_fallback:
        return None
    if tx.filing_gap_pct is not None:
        return max(-0.05, min(0.05, tx.filing_gap_pct / 10))
    return 0.005


def _benchmark_return(
    price_history: dict[str, dict[date, float]],
    current: date,
    as_of: date,
    allow_fallback: bool = True,
) -> float | None:
    prices = price_history.get("SPY", {})
    realized = window_return(prices, current, min(as_of, current + timedelta(days=30)))
    if realized is not None:
        return realized
    if not allow_fallback:
        return None
    return 0.001


def _baselines(
    transactions,
    cfg,
    as_of: date,
    start_date: date,
    price_history: dict[str, dict[date, float]] | None = None,
) -> dict:
    visible = [tx for tx in transactions if start_date <= tx.filing_date <= as_of and tx.tx_type == "buy"]
    spy_return = window_return((price_history or {}).get("SPY", {}), start_date, as_of)
    copy_all_return = 0.003 * len(visible)
    no_gap_count = sum(1 for tx in visible if tx.filing_gap_pct is None or abs(tx.filing_gap_pct) <= cfg["signals"]["max_filing_gap_pct"])
    return {
        "spy": {"total_return": round(spy_return if spy_return is not None else 0.001, 6)},
        "equal_weight_copy_all": {"total_return": round(copy_all_return, 6), "signals": len(visible)},
        "no_entry_after_gap": {"total_return": round(0.004 * no_gap_count, 6), "signals": no_gap_count},
    }
