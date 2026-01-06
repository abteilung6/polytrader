"""Strategy registry for predefined trading strategies."""

from polytrader.core.strategy import ArbitrageStrategy, RandomStrategy, Strategy


def create_strategy(strategy_name: str = "random") -> Strategy:
    """Create a strategy by name.

    Args:
        strategy_name: Name of the strategy (default: "random")

    Returns:
        Strategy instance

    Raises:
        ValueError: If strategy name is unknown
    """
    strategy_name_lower = strategy_name.lower()
    
    if strategy_name_lower == "random":
        return RandomStrategy(
            min_trade_amount=1.0,
            max_trade_amount=1.0,
            trade_probability=0.5,  # 50% chance
        )
    
    if strategy_name_lower == "arbitrage":
        return ArbitrageStrategy(
            max_capital_per_market=100.0,  # Risk limit
            initial_position_pct=0.1,  # 10% per side
            min_profit_threshold=5.0,
            max_price_threshold=0.91,
            trade_amount=10.0,
            min_improvement=0.10,
        )
    
    raise ValueError(f"Unknown strategy: {strategy_name}. Available strategies: random, arbitrage")


def get_strategy_info(strategy_name: str) -> dict[str, str | float]:
    """Get information about a strategy.

    Args:
        strategy_name: Name of the strategy

    Returns:
        Dictionary with strategy information
    """
    strategy = create_strategy(strategy_name)
    if isinstance(strategy, RandomStrategy):
        return {
            "name": strategy_name,
            "type": "Random",
            "min_trade_amount": strategy.min_trade_amount,
            "max_trade_amount": strategy.max_trade_amount,
            "trade_probability": strategy.trade_probability,
        }
    if isinstance(strategy, ArbitrageStrategy):
        return {
            "name": strategy_name,
            "type": "Arbitrage",
            "max_capital_per_market": strategy.max_capital_per_market,
            "initial_position_pct": strategy.initial_position_pct,
            "min_profit_threshold": strategy.min_profit_threshold,
            "max_price_threshold": strategy.max_price_threshold,
            "trade_amount": strategy.trade_amount,
            "min_improvement": strategy.min_improvement,
        }
    return {"name": strategy_name, "type": "Unknown"}

