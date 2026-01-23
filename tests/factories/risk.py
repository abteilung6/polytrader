"""Factories for creating risk-related objects in tests.

Per unit_testing_techinical.mdc §5: All domain objects MUST be created via factories.
"""

from typing import TYPE_CHECKING

from polytrader.risk.engine import RiskEngine
from polytrader.risk.models import RiskContext, RiskLimits

if TYPE_CHECKING:
    from polytrader.events.types import MarketDataEvent, OrderIntentEvent
    from polytrader.risk.policies import Clock
    from polytrader.types import Outcome
else:
    from polytrader.events.types import MarketDataEvent, OrderIntentEvent
    from polytrader.risk.policies import Clock
    from polytrader.types import Outcome


def create_risk_limits(
    max_order_size: float = 10.0,
    max_position_per_market: float = 100.0,
    max_position_global: float = 1000.0,
    max_notional_exposure: float = 5000.0,
    max_trades_per_market: int = 10,
    max_data_staleness_seconds: float = 5.0,
    order_rate_limit_per_minute: int = 60,
    version: str = "1.0",
) -> RiskLimits:
    """Create RiskLimits with deterministic defaults.

    Args:
        max_order_size: Maximum size for a single order (USD)
        max_position_per_market: Maximum position size per market/outcome (USD)
        max_position_global: Maximum total position size across all markets (USD)
        max_notional_exposure: Maximum notional exposure (USD)
        max_trades_per_market: Maximum number of trades per market/outcome
        max_data_staleness_seconds: Maximum age of market data before rejecting (seconds)
        order_rate_limit_per_minute: Maximum orders per minute
        version: Version of the limits

    Returns:
        RiskLimits with specified parameters
    """
    return RiskLimits(
        max_order_size=max_order_size,
        max_position_per_market=max_position_per_market,
        max_position_global=max_position_global,
        max_notional_exposure=max_notional_exposure,
        max_trades_per_market=max_trades_per_market,
        max_data_staleness_seconds=max_data_staleness_seconds,
        order_rate_limit_per_minute=order_rate_limit_per_minute,
        version=version,
    )


def create_risk_engine(
    limits: RiskLimits | None = None,
    clock: Clock | None = None,
) -> RiskEngine:
    """Create RiskEngine with deterministic defaults.

    Args:
        limits: Risk limits (defaults to created from defaults)
        clock: Clock for time-based checks (optional)

    Returns:
        RiskEngine with specified parameters
    """
    if limits is None:
        limits = create_risk_limits()
    return RiskEngine(limits=limits, clock=clock)


def create_risk_context(
    intent: OrderIntentEvent,
    market_data: MarketDataEvent | None = None,
    current_positions: dict[tuple[str, Outcome], float] | None = None,
    reconciliation_healthy: bool = True,
    **kwargs: object,
) -> RiskContext:
    """Create RiskContext with deterministic defaults.

    Args:
        intent: Order intent (required)
        market_data: Market data event (optional)
        current_positions: Current positions dict (defaults to empty)
        reconciliation_healthy: Whether reconciliation is healthy (default: True)
        **kwargs: Additional context fields

    Returns:
        RiskContext with specified parameters
    """
    return RiskContext(
        intent=intent,
        market_data=market_data,
        current_positions=current_positions or {},
        reconciliation_healthy=reconciliation_healthy,
        **kwargs,
    )
