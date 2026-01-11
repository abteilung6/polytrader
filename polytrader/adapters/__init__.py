from collections.abc import AsyncIterator, Callable
from typing import TYPE_CHECKING, Protocol

from polytrader.events.types import MarketDataEvent

if TYPE_CHECKING:
    from polytrader.config import PolymarketSecrets


class IMarketDataAdapter(Protocol):
    """Protocol for market data adapters.

    Adapters provide a stream of market ticks asynchronously.
    """

    def ticks(self) -> AsyncIterator[MarketDataEvent]:
        """Yield market ticks asynchronously.

        This is an async generator that yields MarketDataEvent objects
        continuously. The adapter should handle its own connection
        management, error handling, and retry logic.

        Yields:
            MarketDataEvent: Market data updates

        Raises:
            AdapterError: If connection fails and cannot recover
        """
        ...


def create_adapter_factory(
    secrets: "PolymarketSecrets",
    polling_frequency_hz: float = 1.0,
) -> Callable[[str], IMarketDataAdapter]:
    """Create a factory function for IMarketDataAdapter.

    Args:
        secrets: Polymarket secrets configuration
        polling_frequency_hz: Polling frequency in Hz

    Returns:
        Factory function that takes market_slug and returns adapter
    """
    # Import from polymarket.py module file (not the package)
    # We need to import the module file directly to avoid circular import
    # The package polymarket/__init__.py imports from market_data, which would
    # cause a circular import if we import the package
    from importlib.util import module_from_spec, spec_from_file_location
    from pathlib import Path
    from typing import cast

    # Import the module file directly (polymarket.py, not the package)
    module_path = Path(__file__).parent / "polymarket.py"
    spec = spec_from_file_location("polytrader.adapters.polymarket_module", module_path)
    if spec and spec.loader:
        _polymarket_module = module_from_spec(spec)
        spec.loader.exec_module(_polymarket_module)
        PolymarketAdapterConfig = _polymarket_module.PolymarketAdapterConfig
        PolymarketMarketDataAdapter = _polymarket_module.PolymarketMarketDataAdapter
    else:
        # Fallback: try regular import (may cause circular import)
        from importlib import import_module

        _polymarket_module = import_module("polytrader.adapters.polymarket")
        PolymarketAdapterConfig = _polymarket_module.PolymarketAdapterConfig  # noqa: B009
        PolymarketMarketDataAdapter = _polymarket_module.PolymarketMarketDataAdapter  # noqa: B009

    def factory(market_slug: str) -> IMarketDataAdapter:
        config = PolymarketAdapterConfig(
            market_slug=market_slug,
            polling_frequency_hz=polling_frequency_hz,
            secrets=secrets,
        )
        adapter = PolymarketMarketDataAdapter(config)
        return cast(IMarketDataAdapter, adapter)

    return factory
