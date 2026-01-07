"""Strategy registry for predefined trading strategies."""

from polytrader.core.strategy import (
    GabagoolStrategy,
    Strategy,
)


def create_strategy(strategy_name: str = "gabagool") -> Strategy:
    """Create a strategy by name.

    Args:
        strategy_name: Name of the strategy (default: "gabagool")

    Returns:
        Strategy instance

    Raises:
        ValueError: If strategy name is unknown
    """
    strategy_name_lower = strategy_name.lower()
    
    # Gabagool strategy (asymmetric hedge)
    if strategy_name_lower in ("gabagool", "gaba", "paircost", "asymmetric"):
        return GabagoolStrategy(
            accumulate_price=0.6,  # Buy whichever side hits 0.6 first
            hedge_price=0.3,  # Buy the other side when it hits 0.33 or lower
            max_accumulate_price=0.7,  # Maximum price to buy at when accumulating
            max_buy_price=0.9,  # Maximum price to ever buy at (rejects prices >= 0.92)
            max_ratio=1.4,  # Maximum ratio between sides (e.g., 2.5x)
            min_arbitrage_pair_cost=0.92,  # Minimum arbitrage condition: AVG_YES + AVG_NO must be < 0.95
            max_order_size=5.0,  # Maximum shares to buy in one operation
            min_trade_size=1.0,  # Minimum trade size in USDC
            min_seconds_between_trades=5,  # Rate limiting
            max_capital_per_market=150.0,  # Maximum capital per market
            max_loss_threshold=10.0,  # Maximum acceptable loss in USDC
            lock_profit_threshold=10.0,  # Lock profit when profit exceeds this threshold in USDC
        )

    raise ValueError(
        f"Unknown strategy: {strategy_name}. "
        f"Available strategies: gabagool (aliases: gaba, paircost, asymmetric)"
    )


def get_strategy_info(strategy_name: str) -> dict[str, str | float]:
    """Get information about a strategy.

    Args:
        strategy_name: Name of the strategy

    Returns:
        Dictionary with strategy information
    """
    strategy = create_strategy(strategy_name)
    if isinstance(strategy, GabagoolStrategy):
        strategy_type = "Gabagool (Asymmetric Hedge)"
        return {
            "name": strategy_name,
            "type": strategy_type,
            "accumulate_price": strategy.accumulate_price,
            "hedge_price": strategy.hedge_price,
            "max_accumulate_price": strategy.max_accumulate_price,
            "max_buy_price": strategy.max_buy_price,
            "max_ratio": strategy.max_ratio,
            "min_arbitrage_pair_cost": strategy.min_arbitrage_pair_cost,
            "max_order_size": strategy.max_order_size,
            "min_trade_size": strategy.min_trade_size,
            "min_seconds_between_trades": strategy.min_seconds_between_trades,
            "max_capital_per_market": strategy.max_capital_per_market,
            "max_loss_threshold": strategy.max_loss_threshold,
            "lock_profit_threshold": strategy.lock_profit_threshold,
        }
    return {"name": strategy_name, "type": "Unknown"}
