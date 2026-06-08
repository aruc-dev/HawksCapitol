from __future__ import annotations

import json
from pathlib import Path
import re
from difflib import SequenceMatcher


DEFAULT_ALIASES = {
    "apple inc": "AAPL",
    "apple": "AAPL",
    "microsoft corp": "MSFT",
    "microsoft": "MSFT",
    "nvidia": "NVDA",
    "nvidia corporation": "NVDA",
    "exxon mobil": "XOM",
    "exxon mobil corporation": "XOM",
    "unitedhealth": "UNH",
    "unitedhealth group": "UNH",
    "unitedhealth group inc": "UNH",
    "amazon": "AMZN",
    "amazon com inc": "AMZN",
    "alphabet inc": "GOOGL",
    "alphabet class a": "GOOGL",
    "meta platforms": "META",
    "tesla inc": "TSLA",
    "berkshire hathaway": "BRK.B",
    "jpmorgan chase": "JPM",
    "johnson johnson": "JNJ",
    "visa inc": "V",
    "mastercard": "MA",
    "eli lilly": "LLY",
    "broadcom": "AVGO",
    "costco wholesale": "COST",
    "walmart": "WMT",
    "netflix": "NFLX",
    "home depot": "HD",
    "spy": "SPY",
    "spdr s&p 500 etf trust": "SPY",
}

CORPORATE_SUFFIXES = {
    "class",
    "cl",
    "common",
    "corp",
    "corporation",
    "inc",
    "incorporated",
    "ltd",
    "plc",
    "shares",
    "stock",
    "the",
}


class TickerResolver:
    def __init__(self, aliases: dict[str, str] | None = None) -> None:
        combined = {**DEFAULT_ALIASES, **(aliases or {})}
        self.aliases = {_normalize_name(name): symbol.upper() for name, symbol in combined.items()}

    @classmethod
    def from_sector_file(cls, path: str | Path = "config/sectors.json") -> "TickerResolver":
        if Path(path).exists():
            sectors = json.loads(Path(path).read_text(encoding="utf-8"))
            aliases = {symbol.lower(): symbol.upper() for symbol in sectors}
            return cls(aliases)
        return cls()

    def resolve(self, asset_name: str, ticker: str | None = None) -> str | None:
        if ticker:
            clean = ticker.strip().upper().replace("$", "").replace(" ", "")
            return clean or None
        key = _normalize_name(asset_name)
        if not key:
            return None
        symbol_match = re.search(r"\(([A-Z][A-Z0-9.\-]{0,9})\)", asset_name)
        if symbol_match:
            return symbol_match.group(1).upper()
        symbol_match = re.search(r"\b(?:ticker|symbol)\s*[:\-]\s*([A-Z][A-Z0-9.\-]{0,9})\b", asset_name, flags=re.IGNORECASE)
        if symbol_match:
            return symbol_match.group(1).upper()
        if key in self.aliases:
            return self.aliases[key]
        for alias, symbol in self.aliases.items():
            if alias in key or key in alias:
                return symbol
        best_symbol = None
        best_score = 0.0
        for alias, symbol in self.aliases.items():
            score = SequenceMatcher(None, alias, key).ratio()
            if score > best_score:
                best_symbol = symbol
                best_score = score
        if best_score >= 0.88:
            return best_symbol
        return None


def _normalize_name(value: str) -> str:
    text = value.lower().replace("&", " and ")
    text = re.sub(r"\([^)]*\)", " ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    tokens = [token for token in text.split() if token not in CORPORATE_SUFFIXES and len(token) > 1]
    return " ".join(tokens)
