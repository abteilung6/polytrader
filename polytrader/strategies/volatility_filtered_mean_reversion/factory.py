"""Factory for Volatility-Filtered Mean Reversion strategy.

Per architecture.mdc: Factory creates strategy instances from config.
Factory signature matches registry contract:
    factory(config: dict[str, object], store: IMarketDataStore) -> Callable[[str], IStrategy]
"""

from collections.abc import Callable
from typing import TYPE_CHECKING

from polytrader.strategies.base import IStrategy
from polytrader.strategies.volatility_filtered_mean_reversion.schema import (
    VFMR_SCHEMA,
)

if TYPE_CHECKING:
    from polytrader.store import IMarketDataStore


def create_vfmr_factory(
    config: dict[str, object],
    store: "IMarketDataStore",
) -> Callable[[str], IStrategy]:
    """Create a factory function for VolatilityFilteredMeanReversionStrategy.

    Args:
        config: Strategy configuration (validated against VFMR_SCHEMA)
        store: Market data store for tick history

    Returns:
        Factory function that takes market_slug and returns IStrategy

    Note:
        Config keys: anchor_window, atr_window, ema_fast, ema_slow,
        trend_threshold, entry_z, exit_z, risk_per_trade_pct,
        max_position_notional_pct, max_trades_per_hour,
        cooldown_candles_after_loss. clock=None (default real clock).
    """
    from polytrader.strategies.volatility_filtered_mean_reversion.strategy import (
        VolatilityFilteredMeanReversionStrategy,
    )

    # Apply schema defaults for missing keys
    full = VFMR_SCHEMA.apply_defaults(config)

    def _get_int(key: str) -> int:
        raw = full.get(key)
        if isinstance(raw, int):
            return raw
        if isinstance(raw, float):
            return int(raw)
        return int(full[key])

    def _get_float(key: str) -> float:
        raw = full.get(key)
        if isinstance(raw, (int, float)):
            return float(raw)
        return float(full[key])

    anchor_window = _get_int("anchor_window")
    atr_window = _get_int("atr_window")
    ema_fast = _get_int("ema_fast")
    ema_slow = _get_int("ema_slow")
    trend_threshold = _get_float("trend_threshold")
    entry_z = _get_float("entry_z")
    exit_z = _get_float("exit_z")
    risk_per_trade_pct = _get_float("risk_per_trade_pct")
    max_position_notional_pct = _get_float("max_position_notional_pct")
    max_trades_per_hour = _get_int("max_trades_per_hour")
    cooldown_candles_after_loss = _get_int("cooldown_candles_after_loss")

    def factory(market_slug: str) -> IStrategy:
        return VolatilityFilteredMeanReversionStrategy(
            market_slug=market_slug,
            store=store,
            anchor_window=anchor_window,
            atr_window=atr_window,
            ema_fast=ema_fast,
            ema_slow=ema_slow,
            trend_threshold=trend_threshold,
            entry_z=entry_z,
            exit_z=exit_z,
            risk_per_trade_pct=risk_per_trade_pct,
            max_position_notional_pct=max_position_notional_pct,
            max_trades_per_hour=max_trades_per_hour,
            cooldown_candles_after_loss=cooldown_candles_after_loss,
            clock=None,
        )

    return factory
