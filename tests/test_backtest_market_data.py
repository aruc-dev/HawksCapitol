from __future__ import annotations

from datetime import date
import unittest

from scripts.fetch_backtest_prices import fetch_alpaca_daily_closes


class _FakeBarsResponse:
    def __init__(self, status_code: int, payload: dict) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> dict:
        return self._payload


class _FakeBarsSession:
    def __init__(self, responses: list[_FakeBarsResponse]) -> None:
        self.responses = responses
        self.requests: list[dict] = []

    def get(self, url: str, headers: dict | None = None, params: dict | None = None, timeout: int | None = None) -> _FakeBarsResponse:
        self.requests.append({"url": url, "headers": headers or {}, "params": params or {}, "timeout": timeout})
        return self.responses.pop(0)


class BacktestMarketDataTests(unittest.TestCase):
    def test_fetch_alpaca_daily_closes_uses_batched_adjusted_bars(self) -> None:
        session = _FakeBarsSession(
            [
                _FakeBarsResponse(
                    200,
                    {
                        "bars": {
                            "AAPL": [
                                {"t": "2026-06-01T04:00:00Z", "c": 100.0},
                                {"t": "2026-06-02T04:00:00Z", "c": 101.5},
                            ]
                        }
                    },
                )
            ]
        )

        prices = fetch_alpaca_daily_closes(
            ["AAPL"],
            date(2026, 6, 1),
            date(2026, 6, 7),
            "key-id",
            "secret-key",
            session=session,
        )

        self.assertEqual(prices, {"AAPL": {"2026-06-01": 100.0, "2026-06-02": 101.5}})
        self.assertEqual(session.requests[0]["params"]["symbols"], "AAPL")
        self.assertEqual(session.requests[0]["params"]["adjustment"], "all")
        self.assertEqual(session.requests[0]["params"]["feed"], "iex")
        self.assertEqual(session.requests[0]["headers"]["APCA-API-KEY-ID"], "key-id")


if __name__ == "__main__":
    unittest.main()
