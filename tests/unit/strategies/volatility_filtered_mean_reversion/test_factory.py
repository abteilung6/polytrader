"""Unit tests for VFMR factory.

Per testing.mdc: Factory returns callable that returns IStrategy with correct config.
"""

from polytrader.store import MemoryMarketDataStore
from polytrader.strategies.base import IStrategy
from polytrader.strategies.volatility_filtered_mean_reversion.factory import (
    create_vfmr_factory,
)
from polytrader.strategies.volatility_filtered_mean_reversion.strategy import (
    VolatilityFilteredMeanReversionStrategy,
)


class TestVfmrFactory:
    """Tests for create_vfmr_factory."""

    def test_factory_returns_callable(self) -> None:
        """Factory returns a callable."""
        store = MemoryMarketDataStore()
        config: dict[str, object] = {}
        factory = create_vfmr_factory(config, store)
        assert callable(factory)

    def test_factory_call_returns_istrategy(self) -> None:
        """Calling the returned factory with market_slug returns IStrategy."""
        store = MemoryMarketDataStore()
        config: dict[str, object] = {}
        factory = create_vfmr_factory(config, store)
        strategy = factory("test-market")
        assert isinstance(strategy, IStrategy)
        assert isinstance(strategy, VolatilityFilteredMeanReversionStrategy)
        assert strategy.market_slug == "test-market"

    def test_factory_uses_config_params(self) -> None:
        """Factory passes config params to strategy (anchor_window, entry_z)."""
        store = MemoryMarketDataStore()
        config: dict[str, object] = {"anchor_window": 48, "entry_z": 2.0}
        factory = create_vfmr_factory(config, store)
        strategy = factory("test-market")
        assert isinstance(strategy, VolatilityFilteredMeanReversionStrategy)
        assert strategy.anchor_window == 48
        assert strategy.entry_z == 2.0
        assert strategy.market_slug == "test-market"

    def test_factory_apply_defaults_for_missing_keys(self) -> None:
        """Empty config uses schema defaults."""
        store = MemoryMarketDataStore()
        config: dict[str, object] = {}
        factory = create_vfmr_factory(config, store)
        strategy = factory("test-market")
        assert isinstance(strategy, VolatilityFilteredMeanReversionStrategy)
        assert strategy.anchor_window == 96
        assert strategy.atr_window == 14
        assert strategy.ema_fast == 20
        assert strategy.ema_slow == 80
        assert strategy.trend_threshold == 0.5
        assert strategy.entry_z == 1.5
        assert strategy.exit_z == 0.3
        assert strategy.max_trades_per_hour == 4
