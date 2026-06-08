#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import os
from pathlib import Path
import sys
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backtest.datasets import DEFAULT_BACKTEST_DATASET, DEFAULT_PRICE_HISTORY_DATASET, infer_as_of, load_transactions
from ingestion.storage import write_json


ALPACA_STOCK_BARS_URL = "https://data.alpaca.markets/v2/stocks/bars"
UTC = timezone.utc


def run(
    dataset_path: str | Path = DEFAULT_BACKTEST_DATASET,
    output_path: str | Path = DEFAULT_PRICE_HISTORY_DATASET,
    feed: str = "iex",
    batch_size: int = 50,
    session: Any | None = None,
) -> dict:
    transactions = load_transactions(dataset_path)
    stock_buys = [tx for tx in transactions if tx.tx_type == "buy" and tx.asset_type == "stock" and tx.ticker]
    if not stock_buys:
        raise ValueError(f"backtest dataset has no stock buy transactions: {dataset_path}")
    symbols = sorted({tx.ticker.upper() for tx in stock_buys} | {"SPY"})
    start = min(tx.tx_date for tx in stock_buys)
    end = infer_as_of(transactions)
    key, secret = _alpaca_credentials()
    prices = fetch_alpaca_daily_closes(symbols, start, end, key, secret, feed, batch_size, session=session)
    manifest = {
        "source": "alpaca_market_data",
        "feed": feed,
        "timeframe": "1Day",
        "adjustment": "all",
        "start": start.isoformat(),
        "end": end.isoformat(),
        "pulled_on": datetime.now(UTC).date().isoformat(),
        "symbols_requested": len(symbols),
        "symbols_returned": len(prices),
        "missing_symbols": [symbol for symbol in symbols if symbol not in prices],
    }
    payload = {**manifest, "prices": prices}
    write_json(output_path, payload)
    return manifest


def fetch_alpaca_daily_closes(
    symbols: list[str],
    start: date,
    end: date,
    key: str,
    secret: str,
    feed: str = "iex",
    batch_size: int = 50,
    session: Any | None = None,
) -> dict[str, dict[str, float]]:
    if session is None:
        import requests

        session = requests.Session()
    headers = {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret}
    prices: dict[str, dict[str, float]] = {}
    for offset in range(0, len(symbols), batch_size):
        batch = symbols[offset : offset + batch_size]
        page_token = None
        while True:
            params = {
                "symbols": ",".join(batch),
                "timeframe": "1Day",
                "start": start.isoformat(),
                "end": end.isoformat(),
                "adjustment": "all",
                "feed": feed,
                "limit": 10000,
            }
            if page_token:
                params["page_token"] = page_token
            response = session.get(ALPACA_STOCK_BARS_URL, headers=headers, params=params, timeout=30)
            if response.status_code != 200:
                raise RuntimeError(f"Alpaca market data request failed with HTTP {response.status_code}")
            payload = response.json()
            for symbol, bars in payload.get("bars", {}).items():
                series = prices.setdefault(symbol.upper(), {})
                for bar in bars:
                    day = str(bar["t"])[:10]
                    series[day] = float(bar["c"])
            page_token = payload.get("next_page_token")
            if not page_token:
                break
    return {symbol: series for symbol, series in sorted(prices.items()) if series}


def _alpaca_credentials() -> tuple[str, str]:
    key = os.environ.get("APCA_API_KEY_ID") or os.environ.get("ALPACA_API_KEY") or os.environ.get("ALPACA_PAPER_API_KEY")
    secret = (
        os.environ.get("APCA_API_SECRET_KEY")
        or os.environ.get("ALPACA_SECRET_KEY")
        or os.environ.get("ALPACA_API_SECRET")
        or os.environ.get("ALPACA_PAPER_SECRET_KEY")
    )
    if not key or not secret:
        raise RuntimeError("Alpaca market data credentials are required: set APCA_API_KEY_ID and APCA_API_SECRET_KEY")
    return key, secret


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default=str(DEFAULT_BACKTEST_DATASET))
    parser.add_argument("--output", default=str(DEFAULT_PRICE_HISTORY_DATASET))
    parser.add_argument("--feed", default="iex", choices=["iex", "sip", "otc"])
    parser.add_argument("--batch-size", type=int, default=50)
    args = parser.parse_args()
    print(run(args.dataset, args.output, args.feed, args.batch_size))


if __name__ == "__main__":
    main()
