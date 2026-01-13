"""Event infrastructure for the trading system."""

from polytrader.events.bus import EventBus, Topic
from polytrader.events.store import IEventStore, MemoryEventStore

# Import event types first
from polytrader.events.types import (
    CircuitBreakerEvent,
    ConfigLoadedEvent,
    Event,
    EventSource,
    ExecutionErrorEvent,
    ExecutionPermitEvent,
    ExecutionRequestEvent,
    ExecutionResponseEvent,
    FillEvent,
    KillSwitchEvent,
    MarketChangeEvent,
    MarketDataEvent,
    MarketDiscoveryEvent,
    OrderAckEvent,
    OrderCanceledEvent,
    OrderCreatedEvent,
    OrderExecutedEvent,
    OrderIntentEvent,
    OrderRejectedEvent,
    OrderSubmittedEvent,
    ReconcileEvent,
    RiskCheckEvent,
    ServiceErrorEvent,
    ServiceStartedEvent,
    ServiceStoppedEvent,
    SignalEvent,
    SystemStartedEvent,
    SystemStoppedEvent,
    TargetEvent,
)

__all__ = [
    "APPROVED_PROPOSALS",
    "CANCEL_ORDER_COMMANDS",
    "CircuitBreakerEvent",
    "ConfigLoadedEvent",
    "Event",
    "EventBus",
    "EventSource",
    "EXECUTION_ERRORS",
    "EXECUTION_REQUESTS",
    "EXECUTION_RESPONSES",
    "ExecutionErrorEvent",
    "ExecutionPermitEvent",
    "ExecutionRequestEvent",
    "ExecutionResponseEvent",
    "FillEvent",
    "FILLS",
    "IEventStore",
    "KillSwitchEvent",
    "MARKET_CHANGE",
    "MARKET_DATA",
    "MARKET_DISCOVERY",
    "MarketChangeEvent",
    "MarketDataEvent",
    "MarketDiscoveryEvent",
    "MemoryEventStore",
    "OrderAckEvent",
    "ORDER_ACKS",
    "ORDER_CANCELS",
    "ORDER_CREATED",
    "ORDER_REJECTS",
    "ORDER_SUBMITTED",
    "OrderCanceledEvent",
    "OrderCreatedEvent",
    "OrderExecutedEvent",
    "OrderIntentEvent",
    "OrderRejectedEvent",
    "OrderSubmittedEvent",
    "ORDERS",
    "CIRCUIT_BREAKER",
    "PROPOSALS",
    "RECONCILE",
    "ReconcileEvent",
    "RISK_CHECKS",
    "RiskCheckEvent",
    "ServiceErrorEvent",
    "ServiceStartedEvent",
    "ServiceStoppedEvent",
    "SIGNALS",
    "SignalEvent",
    "SUBMIT_ORDER_COMMANDS",
    "SYSTEM_LIFECYCLE",
    "SystemStartedEvent",
    "SystemStoppedEvent",
    "TARGETS",
    "TargetEvent",
    "Topic",
    "USER_STREAM_ACKS",
    "USER_STREAM_CANCELS",
    "USER_STREAM_FILLS",
    "USER_STREAM_REJECTS",
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
    elif name == "EXECUTION_REQUESTS":
        from polytrader.events.topics import get_execution_requests_topic

        return get_execution_requests_topic()
    elif name == "EXECUTION_RESPONSES":
        from polytrader.events.topics import get_execution_responses_topic

        return get_execution_responses_topic()
    elif name == "EXECUTION_ERRORS":
        from polytrader.events.topics import get_execution_errors_topic

        return get_execution_errors_topic()
    elif name == "MARKET_DISCOVERY":
        from polytrader.events.topics import get_market_discovery_topic

        return get_market_discovery_topic()
    elif name == "SIGNALS":
        from polytrader.events.topics import get_signals_topic

        return get_signals_topic()
    elif name == "TARGETS":
        from polytrader.events.topics import get_targets_topic

        return get_targets_topic()
    elif name == "USER_STREAM_ACKS":
        from polytrader.events.topics import get_user_stream_acks_topic

        return get_user_stream_acks_topic()
    elif name == "USER_STREAM_REJECTS":
        from polytrader.events.topics import get_user_stream_rejects_topic

        return get_user_stream_rejects_topic()
    elif name == "USER_STREAM_FILLS":
        from polytrader.events.topics import get_user_stream_fills_topic

        return get_user_stream_fills_topic()
    elif name == "USER_STREAM_CANCELS":
        from polytrader.events.topics import get_user_stream_cancels_topic

        return get_user_stream_cancels_topic()
    elif name == "RECONCILE":
        from polytrader.events.topics import get_reconcile_topic

        return get_reconcile_topic()
    elif name == "CIRCUIT_BREAKER":
        from polytrader.events.topics import get_circuit_breaker_topic

        return get_circuit_breaker_topic()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


# Rebuild RiskCheckEvent after all imports to resolve forward references
# This is safe because risk.models imports events.types only in TYPE_CHECKING
from polytrader.risk.models import RiskResult  # noqa: E402, F401

RiskCheckEvent.model_rebuild()
