from __future__ import annotations

import json
from pathlib import Path


DEFAULT_ALIASES = {
    "apple inc": "AAPL",
    "apple": "AAPL",
    "microsoft corp": "MSFT",
    "microsoft": "MSFT",
    "nvidia": "NVDA",
    "nvidia corporation": "NVDA",
    "exxon mobil": "XOM",
    "unitedhealth": "UNH",
    "spy": "SPY",
}


class TickerResolver:
    def __init__(self, aliases: dict[str, str] | None = None) -> None:
        self.aliases = {**DEFAULT_ALIASES, **(aliases or {})}

    @classmethod
    def from_sector_file(cls, path: str | Path = "config/sectors.json") -> "TickerResolver":
        if Path(path).exists():
            sectors = json.loads(Path(path).read_text(encoding="utf-8"))
            aliases = {symbol.lower(): symbol.upper() for symbol in sectors}
            return cls(aliases)
        return cls()

    def resolve(self, asset_name: str, ticker: str | None = None) -> str | None:
        if ticker:
            clean = ticker.strip().upper().replace("$", "")
            return clean or None
        key = asset_name.lower().replace(".", "").strip()
        if key in self.aliases:
            return self.aliases[key]
        for alias, symbol in self.aliases.items():
            if alias in key or key in alias:
                return symbol
        return None
