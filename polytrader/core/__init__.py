"""Core portfolio management and trading system."""

from polytrader.core.manager import PortfolioManager
from polytrader.core.portfolio import Portfolio
from polytrader.core.position import Position
from polytrader.core.strategy import (
    GabagoolStrategy,
    Strategy,
)
from polytrader.core.strategy_registry import create_strategy, get_strategy_info
from polytrader.core.trade import TradeDecision

# Import V2 strategy (optional, may not be available)
from polytrader.core.strategies.gabagool.v2 import GabagoolV2Strategy

__all__ = [
    "GabagoolStrategy",
    "GabagoolV2Strategy",
    "Portfolio",
    "PortfolioManager",
    "Position",
    "Strategy",
    "TradeDecision",
    "create_strategy",
    "get_strategy_info",
]
