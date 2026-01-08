"""Strategy registry for predefined trading strategies.

This module provides backward compatibility by delegating to the new strategies module.
"""

from polytrader.core.strategies import create_strategy, get_strategy_info

__all__ = ["create_strategy", "get_strategy_info"]
