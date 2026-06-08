from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any


def parse_date(value: str | date | datetime | None) -> date | None:
    if value is None or isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    text = str(value).strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    return date.fromisoformat(text[:10])


@dataclass(frozen=True)
class Member:
    member_id: str
    full_name: str
    chamber: str
    party: str = ""
    state: str = ""
    committees: tuple[str, ...] = ()
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True)
class Disclosure:
    doc_id: str
    source: str
    member_id: str
    filing_date: date
    ingested_at: datetime
    url: str = ""
    parse_confidence: float = 1.0
    amends_doc_id: str | None = None


@dataclass(frozen=True)
class Transaction:
    tx_id: str
    doc_id: str
    member_id: str
    asset_name_raw: str
    ticker: str | None
    asset_type: str
    tx_type: str
    tx_date: date
    filing_date: date
    amount_min: float
    amount_max: float
    amount_mid: float
    owner: str = "self"
    source: str = "unknown"
    source_quality: str = "official"
    parse_confidence: float = 1.0
    option_meta: dict[str, Any] | None = None
    filing_lag_days: int = 0
    price_on_tx_date: float | None = None
    price_on_filing_date: float | None = None
    filing_gap_pct: float | None = None
    dedup_key: str = ""
    raw_ref: str = ""
    amends_doc_id: str | None = None


@dataclass
class Signal:
    signal_id: str
    created_at: datetime
    ticker: str
    asset_type: str
    side: str
    source_tx_ids: list[str]
    conviction_score: float
    freshness_score: float
    entry_quality_score: float
    target_weight_pct: float
    rationale: str
    blocked_reason: str | None = None


@dataclass
class Position:
    trade_id: str
    ticker: str
    asset_type: str
    entry_date: date
    entry_price: float
    qty: float
    stop_price: float
    target_price: float
    trail_high: float
    copy_basis_tx_ids: list[str] = field(default_factory=list)
    member_ids: list[str] = field(default_factory=list)
    status: str = "open"
    exit_date: date | None = None
    exit_price: float | None = None
    realized_pnl: float | None = None
    exit_reason: str | None = None
    option_meta: dict[str, Any] | None = None


@dataclass(frozen=True)
class MemberScore:
    member_id: str
    as_of_date: date
    n_trades: int
    hit_rate: float
    avg_alpha_30d: float
    avg_alpha_90d: float
    median_hold: int
    filing_latency_days: float
    sector_concentration: float
    sample_quality: float
    score: float


@dataclass(frozen=True)
class MarketSnapshot:
    as_of: date
    prices: dict[str, float]
    regime_ok: bool = True
    stale_symbols: set[str] = field(default_factory=set)
    last_prices: dict[str, float] = field(default_factory=dict)
    events: dict[str, set[str]] = field(default_factory=dict)
    option_metrics: dict[str, dict[str, float]] = field(default_factory=dict)

    def price(self, ticker: str) -> float | None:
        return self.prices.get(ticker.upper())

    def effective_price(self, ticker: str) -> float | None:
        symbol = ticker.upper()
        return self.prices.get(symbol) if symbol not in self.stale_symbols else self.last_prices.get(symbol, self.prices.get(symbol))


@dataclass(frozen=True)
class ExitDecision:
    ticker: str
    reason: str
    action: str = "exit"
    price: float | None = None
    priority: int = 100


@dataclass(frozen=True)
class Order:
    client_order_id: str
    ticker: str
    side: str
    qty: float
    order_type: str = "market"
    asset_type: str = "stock"
    limit_price: float | None = None


@dataclass(frozen=True)
class OrderResult:
    client_order_id: str
    ticker: str
    side: str
    qty: float
    status: str
    message: str = ""


@dataclass(frozen=True)
class BrokerPosition:
    ticker: str
    qty: float
    avg_entry_price: float
    asset_type: str = "stock"
