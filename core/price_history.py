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
    if not series:
        return None
    dates = sorted(series)
    start_idx = bisect_left(dates, start)
    end_idx = bisect_right(dates, end) - 1
    if start_idx >= len(dates) or end_idx < 0:
        return None
    start_day = dates[start_idx]
    end_day = dates[end_idx]
    start_value = series[start_day]
    end_value = series[end_day]
    if end_day < start_day or start_value <= 0:
        return None
    return (end_value - start_value) / start_value
