"""Test factories for creating domain objects.

Per unit_testing_techinical.mdc §5: All domain objects MUST be created via factories.
Factories have deterministic defaults and require explicit overrides for risk/size/price fields.
"""

from tests.factories.clocks import (
    FixedClock,
    create_fixed_clock,
    create_mock_clock,
)
from tests.factories.events import (
    create_fill_event,
    create_market_data_event,
    create_order_intent_event,
    create_signal_event,
)
from tests.factories.orders import create_order
from tests.factories.risk import (
    create_risk_context,
    create_risk_engine,
    create_risk_limits,
)

__all__ = [
    # Events
    "create_order_intent_event",
    "create_signal_event",
    "create_market_data_event",
    "create_fill_event",
    # Orders
    "create_order",
    # Risk
    "create_risk_limits",
    "create_risk_engine",
    "create_risk_context",
    # Clocks
    "FixedClock",
    "create_fixed_clock",
    "create_mock_clock",
]
