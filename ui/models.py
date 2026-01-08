"""Data models for the UI."""

from dataclasses import dataclass


@dataclass
class TradeEvent:
    """Record of a trade execution."""

    timestamp: float
    outcome: str
    amount: float
    price: float
    shares: float
    balance: float
    up_price: float
    down_price: float


@dataclass
class PricePoint:
    """Price data point at a timestamp."""

    timestamp: float
    up_price: float
    down_price: float
    balance: float
    up_shares: float
    down_shares: float


@dataclass
class MarketProfitResult:
    """Profit result for a single market."""

    market_id: str
    profit: float
    profit_pct: float
    final_balance: float
    total_trades: int
    total_spent: float
    final_up_shares: float
    final_down_shares: float
    profit_if_up_wins: float
    profit_if_down_wins: float

