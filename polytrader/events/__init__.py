"""Event infrastructure for the trading system."""

from polytrader.events.bus import EventBus, Topic
from polytrader.events.store import IEventStore, MemoryEventStore
from polytrader.events.types import (
    ConfigLoadedEvent,
    Event,
    EventSource,
    RiskCheckEvent,
    SystemStartedEvent,
    SystemStoppedEvent,
)

__all__ = [
    "ConfigLoadedEvent",
    "Event",
    "EventBus",
    "EventSource",
    "IEventStore",
    "MARKET_CHANGE",
    "MARKET_DATA",
    "MemoryEventStore",
    "ORDERS",
    "PROPOSALS",
    "RISK_CHECKS",
    "RiskCheckEvent",
    "SYSTEM_LIFECYCLE",
    "SystemStartedEvent",
    "SystemStoppedEvent",
    "Topic",
]


def __getattr__(name: str):
    """Lazily import topic constants from topics module.

    This defers topic initialization until after all modules are fully loaded,
    breaking the circular import between polytrader.types and polytrader.events.

    Args:
        name: Name of the topic constant to retrieve

    Returns:
        The requested Topic instance

    Raises:
        AttributeError: If the requested topic name is not recognized
    """
    if name == "MARKET_DATA":
        from polytrader.events.topics import get_market_data_topic

        return get_market_data_topic()
    elif name == "PROPOSALS":
        from polytrader.events.topics import get_proposals_topic

        return get_proposals_topic()
    elif name == "ORDERS":
        from polytrader.events.topics import get_orders_topic

        return get_orders_topic()
    elif name == "MARKET_CHANGE":
        from polytrader.events.topics import get_market_change_topic

        return get_market_change_topic()
    elif name == "SYSTEM_LIFECYCLE":
        from polytrader.events.topics import get_system_lifecycle_topic

        return get_system_lifecycle_topic()
    elif name == "RISK_CHECKS":
        from polytrader.events.topics import get_risk_checks_topic

        return get_risk_checks_topic()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
