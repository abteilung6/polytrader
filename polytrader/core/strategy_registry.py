"""Strategy registry for predefined trading strategies."""

from polytrader.core.strategy import RandomStrategy, Strategy


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

    raise ValueError(
        f"Unknown strategy: {strategy_name}. "
        f"Available strategies: random"
    )


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
    return {"name": strategy_name, "type": "Unknown"}
