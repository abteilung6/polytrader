"""Strategy registry for predefined trading strategies."""

from polytrader.core.strategy import Strategy

# Import all versions from strategies module (flattened structure)
from polytrader.core.strategies.gabagool_v1 import GabagoolStrategy
from polytrader.core.strategies.gabagool_v2 import GabagoolV2Strategy
from polytrader.core.strategies.gabagool_v3 import GabagoolV3Strategy
from polytrader.core.strategies.gabagool_v4 import GabagoolV4Strategy
from polytrader.core.strategies.gabagool_v5 import GabagoolV5Strategy
from polytrader.core.strategies.gabagool_v6 import GabagoolV6Strategy


def create_strategy(strategy_name: str = "gabagool") -> Strategy:
    """Create a strategy by name.

    Args:
        strategy_name: Name of the strategy (default: "gabagool")
            - "gabagool" or "gabagool-v1" → Original GabagoolStrategy (V1)
            - "gabagool-v2" or "gabagool2" → GabagoolV2Strategy (V2)
            - "gabagool-v3" or "gabagool3" → GabagoolV3Strategy (V3 - Rebalancing)
            - "gabagool-v4" or "gabagool4" → GabagoolV4Strategy (V4 - Winner at 0.6)
            - "gabagool-v5" or "gabagool5" → GabagoolV5Strategy (V5 - V4 with auto-hedging)
            - "gabagool-v6" or "gabagool6" → GabagoolV6Strategy (V6 - V4 with 3-minute trading cutoff)

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
        return GabagoolV4Strategy(
            target_profit_usdc=10.0,
            winner_threshold=0.6,
            max_buy_price=0.82,
            min_trade_amount_usdc=1.0,
            max_capital_per_market_usdc=1000.0,
        )
    # New Gabagool V5 (V4 with automatic loss hedging)
    if strategy_name_lower in ("gabagool-v5", "gabagool5", "gaba-v5"):
        return GabagoolV5Strategy(
            target_profit_usdc=10.0,
            winner_threshold=0.6,
            max_buy_price=0.82,
            min_trade_amount_usdc=1.0,
            max_capital_per_market_usdc=2000.0,
            hedge_loss_threshold=10.0,  # Auto-hedge when loss > $50
            max_hedge_price=0.8,  # Max price to pay for hedging
        )
    # New Gabagool V6 (V4 with automatic hedging when worst-case loss exceeds threshold)
    if strategy_name_lower in ("gabagool-v6", "gabagool6", "gaba-v6"):
        return GabagoolV6Strategy(
            target_profit_usdc=10.0,
            winner_threshold=0.6,
            max_buy_price=0.82,
            min_trade_amount_usdc=1.0,
            max_capital_per_market_usdc=1000.0,
            worst_case_loss_threshold=40.0,  # Hedge when worst-case loss > $100
        )
    if strategy_name_lower in ("gabagool-small", "gabagool-small", "gaba-small"):
        return GabagoolV4Strategy(
            target_profit_usdc=5.0,
            winner_threshold=0.6,
            max_buy_price=0.82,
            min_trade_amount_usdc=1.0,
            max_capital_per_market_usdc=200.0,
        )
    raise ValueError(
        f"Unknown strategy: {strategy_name}. "
        f"Available strategies: gabagool (aliases: gaba, paircost, asymmetric, gabagool-v1), "
        f"gabagool-v2 (aliases: gabagool2, gaba-v2), "
        f"gabagool-v3 (aliases: gabagool3, gaba-v3), "
        f"gabagool-v4 (aliases: gabagool4, gaba-v4), "
        f"gabagool-v5 (aliases: gabagool5, gaba-v5), "
        f"gabagool-v6 (aliases: gabagool6, gaba-v6), "
        f"gabagool-small (aliases: gabagool-small, gaba-small)"
    )

