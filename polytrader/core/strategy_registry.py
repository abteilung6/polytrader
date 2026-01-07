"""Strategy registry for predefined trading strategies."""

from polytrader.core.strategy import (
    GabagoolStrategy,
    GabagoolV2Strategy,
    GabagoolV3Strategy,
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
            hedge_price=0.35,  # Buy the other side when it hits 0.33 or lower
            max_accumulate_price=0.64,  # Maximum price to buy at when accumulating
            max_buy_price=0.9,  # Maximum price to ever buy at (rejects prices >= 0.92)
            max_ratio=1.6,  # Maximum ratio between sides (e.g., 2.5x)
            min_arbitrage_pair_cost=0.92,  # Minimum arbitrage condition: AVG_YES + AVG_NO must be < 0.95
            max_order_size=20.0,  # Maximum shares to buy in one operation
            min_trade_size=2.0,  # Minimum trade size in USDC
            min_seconds_between_trades=20,  # Rate limiting
            max_capital_per_market=150.0,  # Maximum capital per market
            max_loss_threshold=10.0,  # Maximum acceptable loss in USDC (also stops if profit > this)
        )
    
    # Gabagool V2 strategy (with laggard prioritization)
    if strategy_name_lower in ("gabagoolv2", "gabav2", "gaba2", "laggard"):
        return GabagoolV2Strategy(
            accumulate_price=0.6,  # Buy whichever side hits 0.6 first
            hedge_price=0.35,  # Buy the other side when it hits 0.33 or lower
            max_accumulate_price=0.64,  # Maximum price to buy at when accumulating
            max_buy_price=0.9,  # Maximum price to ever buy at (rejects prices >= 0.92)
            max_ratio=1.6,  # Maximum ratio between sides (e.g., 2.5x)
            min_arbitrage_pair_cost=0.92,  # Minimum arbitrage condition: AVG_YES + AVG_NO must be < 0.95
            max_order_size=20.0,  # Maximum shares to buy in one operation
            min_trade_size=2.0,  # Minimum trade size in USDC
            min_seconds_between_trades=20,  # Rate limiting
            max_capital_per_market=200.0,  # Maximum capital per market
            max_loss_threshold=10.0,  # Maximum acceptable loss in USDC (also stops if profit > this)
        )
    
    # Gabagool V3 strategy (confidence-based - buys more expensive option)
    if strategy_name_lower in ("gabagoolv3", "gabav3", "gaba3", "confidence", "momentum"):
        return GabagoolV3Strategy(
            accumulate_price=0.6,  # Buy whichever side hits 0.6 first
            hedge_price=0.35,  # Buy the other side when it hits 0.33 or lower
            max_accumulate_price=0.64,  # Maximum price to buy at when accumulating
            max_buy_price=0.9,  # Maximum price to ever buy at (rejects prices >= 0.92)
            max_ratio=1.6,  # Maximum ratio between sides (e.g., 2.5x)
            min_arbitrage_pair_cost=0.92,  # Minimum arbitrage condition: AVG_YES + AVG_NO must be < 0.95
            max_order_size=20.0,  # Maximum shares to buy in one operation
            min_trade_size=2.0,  # Minimum trade size in USDC
            min_seconds_between_trades=20,  # Rate limiting
            max_capital_per_market=150.0,  # Maximum capital per market
            max_loss_threshold=10.0,  # Maximum acceptable loss in USDC (also stops if profit > this)
        )

    raise ValueError(
        f"Unknown strategy: {strategy_name}. "
        f"Available strategies: gabagool (aliases: gaba, paircost, asymmetric), "
        f"gabagoolv2 (aliases: gabav2, gaba2, laggard), "
        f"gabagoolv3 (aliases: gabav3, gaba3, confidence, momentum)"
    )


def get_strategy_info(strategy_name: str) -> dict[str, str | float]:
    """Get information about a strategy.

    Args:
        strategy_name: Name of the strategy

    Returns:
        Dictionary with strategy information
    """
    strategy = create_strategy(strategy_name)
    if isinstance(strategy, (GabagoolStrategy, GabagoolV2Strategy, GabagoolV3Strategy)):
        if isinstance(strategy, GabagoolV3Strategy):
            strategy_type = "Gabagool V3 (Confidence-Based)"
        elif isinstance(strategy, GabagoolV2Strategy):
            strategy_type = "Gabagool V2 (Laggard Prioritization)"
        else:
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
        }
    return {"name": strategy_name, "type": "Unknown"}
