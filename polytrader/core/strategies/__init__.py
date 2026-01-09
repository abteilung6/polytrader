"""Strategy registry for predefined trading strategies."""

from polytrader.core.strategy import Strategy

# Import all versions from strategies module
from polytrader.core.strategies.gabagool.v1 import GabagoolStrategy
from polytrader.core.strategies.gabagool.v2 import GabagoolV2Strategy
from polytrader.core.strategies.gabagool.v3 import GabagoolV3Strategy
from polytrader.core.strategies.gabagool.v4 import GabagoolV4Strategy


def create_strategy(strategy_name: str = "gabagool") -> Strategy:
    """Create a strategy by name.

    Args:
        strategy_name: Name of the strategy (default: "gabagool")
            - "gabagool" or "gabagool-v1" → Original GabagoolStrategy (V1)
            - "gabagool-v2" or "gabagool2" → GabagoolV2Strategy (V2)
            - "gabagool-v3" or "gabagool3" → GabagoolV3Strategy (V3 - Rebalancing)
            - "gabagool-v4" or "gabagool4" → GabagoolV4Strategy (V4 - Winner at 0.6)

    Returns:
        Strategy instance

    Raises:
        ValueError: If strategy name is unknown
    """
    strategy_name_lower = strategy_name.lower()
    
    # Original Gabagool V1 (keep existing)
    if strategy_name_lower in ("gabagool", "gaba", "paircost", "asymmetric", "gabagool-v1"):
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
    
    # New Gabagool V2
    if strategy_name_lower in ("gabagool-v2", "gabagool2", "gaba-v2"):
        if GabagoolV2Strategy is None:
            raise ValueError(
                f"GabagoolV2Strategy not yet implemented. "
                f"Available strategies: gabagool (aliases: gaba, paircost, asymmetric, gabagool-v1)"
            )
        return GabagoolV2Strategy(
            seconds_between_trades=10.0,
            min_trade_amount_usdc=1.0,
            max_capital_per_market_usdc=1000.0,
            max_shares_per_trade=5.0,
            share_ratio=1.3,
            max_buy_price=0.8,
        )
    # New Gabagool V3 (Rebalancing)
    if strategy_name_lower in ("gabagool-v3", "gabagool3", "gaba-v3"):
        if GabagoolV3Strategy is None:
            raise ValueError(
                f"GabagoolV3Strategy not yet implemented. "
                f"Available strategies: gabagool (aliases: gaba, paircost, asymmetric, gabagool-v1), "
                f"gabagool-v2 (aliases: gabagool2, gaba-v2)"
            )
        return GabagoolV3Strategy(
            seconds_between_trades=10.0,
            min_trade_amount_usdc=1.0,
            max_capital_per_market_usdc=5000.0,
            min_shares_per_trade=2.0,
            share_ratio=1.3,
            max_buy_price=0.8,
        )
    # New Gabagool V4 (Winner at 0.6)
    if strategy_name_lower in ("gabagool-v4", "gabagool4", "gaba-v4"):
        if GabagoolV4Strategy is None:
            raise ValueError(
                f"GabagoolV4Strategy not yet implemented. "
                f"Available strategies: gabagool (aliases: gaba, paircost, asymmetric, gabagool-v1), "
                f"gabagool-v2 (aliases: gabagool2, gaba-v2), "
                f"gabagool-v3 (aliases: gabagool3, gaba-v3)"
            )
        return GabagoolV4Strategy(
            target_profit_usdc=5.0,
            winner_threshold=0.6,
            other_side_hold_duration_seconds=20.0,
            max_buy_price=0.80,
            min_trade_amount_usdc=1.0,
            max_capital_per_market_usdc=500.0,
        )
    raise ValueError(
        f"Unknown strategy: {strategy_name}. "
        f"Available strategies: gabagool (aliases: gaba, paircost, asymmetric, gabagool-v1), "
        f"gabagool-v2 (aliases: gabagool2, gaba-v2), "
        f"gabagool-v3 (aliases: gabagool3, gaba-v3), "
        f"gabagool-v4 (aliases: gabagool4, gaba-v4)"
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
        strategy_type = "Gabagool V1 (Asymmetric Hedge)"
        return {
            "name": strategy_name,
            "type": strategy_type,
            "version": "v1",
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
    elif GabagoolV2Strategy is not None and isinstance(strategy, GabagoolV2Strategy):
        strategy_type = "Gabagool V2 (Continuous Buying Strategy)"
        return {
            "name": strategy_name,
            "type": strategy_type,
            "version": "v2",
            "min_trade_amount_usdc": strategy.min_trade_amount_usdc,
            "seconds_between_trades": strategy.seconds_between_trades,
            "max_capital_per_market_usdc": strategy.max_capital_per_market_usdc,
            "max_shares_per_trade": strategy.max_shares_per_trade,
            "share_ratio": strategy.share_ratio,
            "max_buy_price": strategy.max_buy_price,
        }
    elif GabagoolV3Strategy is not None and isinstance(strategy, GabagoolV3Strategy):
        strategy_type = "Gabagool V3 (Rebalancing Continuous Buying Strategy)"
        return {
            "name": strategy_name,
            "type": strategy_type,
            "version": "v3",
            "min_trade_amount_usdc": strategy.min_trade_amount_usdc,
            "seconds_between_trades": strategy.seconds_between_trades,
            "max_capital_per_market_usdc": strategy.max_capital_per_market_usdc,
            "min_shares_per_trade": strategy.min_shares_per_trade,
            "share_ratio": strategy.share_ratio,
            "max_buy_price": strategy.max_buy_price,
            "price_equality_threshold": strategy.price_equality_threshold,
        }
    elif GabagoolV4Strategy is not None and isinstance(strategy, GabagoolV4Strategy):
        strategy_type = "Gabagool V4 (Winner at 0.6)"
        return {
            "name": strategy_name,
            "type": strategy_type,
            "version": "v4",
            "target_profit_usdc": strategy.target_profit_usdc,
            "winner_threshold": strategy.winner_threshold,
            "other_side_hold_duration_seconds": strategy.other_side_hold_duration_seconds,
            "max_buy_price": strategy.max_buy_price,
            "min_trade_amount_usdc": strategy.min_trade_amount_usdc,
            "max_capital_per_market_usdc": strategy.max_capital_per_market_usdc,
        }
    return {"name": strategy_name, "type": "Unknown"}

