from __future__ import annotations

from bisect import bisect_left, bisect_right
from datetime import date


def price_on_or_after(series: dict[date, float], target: date) -> tuple[date, float] | None:
    if not series:
        return None
    dates = sorted(series)
    idx = bisect_left(dates, target)
    if idx >= len(dates):
        return None
    day = dates[idx]
    return day, series[day]


def price_on_or_before(series: dict[date, float], target: date) -> tuple[date, float] | None:
    if not series:
        return None
    dates = sorted(series)
    idx = bisect_right(dates, target) - 1
    if idx < 0:
        return None
    day = dates[idx]
    return day, series[day]


def window_return(series: dict[date, float], start: date, end: date) -> float | None:
    start_price = price_on_or_after(series, start)
    end_price = price_on_or_before(series, end)
    if not start_price or not end_price:
        return None
    start_day, start_value = start_price
    end_day, end_value = end_price
    if end_day < start_day or start_value <= 0:
        return None
    return (end_value - start_value) / start_value
