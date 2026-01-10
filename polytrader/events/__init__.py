"""Event infrastructure for the trading system."""

from polytrader.events.bus import EventBus, Topic
from polytrader.events.store import IEventStore, MemoryEventStore
from polytrader.events.types import (
    ConfigLoadedEvent,
    Event,
    EventSource,
    FillEvent,
    OrderAckEvent,
    OrderCanceledEvent,
    OrderCreatedEvent,
    OrderRejectedEvent,
    OrderSubmittedEvent,
    RiskCheckEvent,
    SystemStartedEvent,
    SystemStoppedEvent,
)

__all__ = [
    "APPROVED_PROPOSALS",
    "CANCEL_ORDER_COMMANDS",
    "ConfigLoadedEvent",
    "Event",
    "EventBus",
    "EventSource",
    "FillEvent",
    "FILLS",
    "IEventStore",
    "MARKET_CHANGE",
    "MARKET_DATA",
    "MemoryEventStore",
    "OrderAckEvent",
    "ORDER_ACKS",
    "ORDER_CANCELS",
    "ORDER_CREATED",
    "ORDER_REJECTS",
    "ORDER_SUBMITTED",
    "OrderCanceledEvent",
    "OrderCreatedEvent",
    "OrderRejectedEvent",
    "OrderSubmittedEvent",
    "ORDERS",
    "PROPOSALS",
    "RISK_CHECKS",
    "RiskCheckEvent",
    "SUBMIT_ORDER_COMMANDS",
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
    elif name == "APPROVED_PROPOSALS":
        from polytrader.events.topics import get_approved_proposals_topic

        return get_approved_proposals_topic()
    elif name == "ORDER_CREATED":
        from polytrader.events.topics import get_order_created_topic

        return get_order_created_topic()
    elif name == "ORDER_SUBMITTED":
        from polytrader.events.topics import get_order_submitted_topic

        return get_order_submitted_topic()
    elif name == "ORDER_ACKS":
        from polytrader.events.topics import get_order_acks_topic

        return get_order_acks_topic()
    elif name == "ORDER_REJECTS":
        from polytrader.events.topics import get_order_rejects_topic

        return get_order_rejects_topic()
    elif name == "FILLS":
        from polytrader.events.topics import get_fills_topic

        return get_fills_topic()
    elif name == "ORDER_CANCELS":
        from polytrader.events.topics import get_order_cancels_topic

        return get_order_cancels_topic()
    elif name == "SUBMIT_ORDER_COMMANDS":
        from polytrader.events.topics import get_submit_order_commands_topic

        return get_submit_order_commands_topic()
    elif name == "CANCEL_ORDER_COMMANDS":
        from polytrader.events.topics import get_cancel_order_commands_topic

        return get_cancel_order_commands_topic()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
