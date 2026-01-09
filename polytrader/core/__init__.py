"""Core portfolio management and trading system."""

from polytrader.core.manager import PortfolioManager
from polytrader.core.portfolio import Portfolio
from polytrader.core.position import Position
from polytrader.core.strategy import Strategy
from polytrader.core.strategies import create_strategy
from polytrader.core.trade import TradeDecision

# Import strategies
from polytrader.core.strategies.gabagool_v1 import GabagoolStrategy
from polytrader.core.strategies.gabagool_v2 import GabagoolV2Strategy

__all__ = [
    "GabagoolStrategy",
    "GabagoolV2Strategy",
    "Portfolio",
    "PortfolioManager",
    "Position",
    "Strategy",
    "TradeDecision",
    "create_strategy",
]
