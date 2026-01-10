"""Topic constants for event bus."""

from polytrader.events.bus import Topic

# Lazy initialization to avoid circular imports
_market_data_topic: Topic | None = None
_proposals_topic: Topic | None = None
_orders_topic: Topic | None = None
_market_change_topic: Topic | None = None
_system_lifecycle_topic: Topic | None = None
_risk_checks_topic: Topic | None = None
_approved_proposals_topic: Topic | None = None
_order_created_topic: Topic | None = None
_order_submitted_topic: Topic | None = None
_order_acks_topic: Topic | None = None
_order_rejects_topic: Topic | None = None
_fills_topic: Topic | None = None
_order_cancels_topic: Topic | None = None


def _create_market_data_topic() -> Topic:
    """Create the MARKET_DATA topic."""
    from polytrader.types import MarketDataEvent

    return Topic[MarketDataEvent]("market_data")


def _create_proposals_topic() -> Topic:
    """Create the PROPOSALS topic."""
    from polytrader.types import OrderIntentEvent

    return Topic[OrderIntentEvent]("proposals")


def _create_orders_topic() -> Topic:
    """Create the ORDERS topic."""
    from polytrader.types import OrderExecutedEvent

    return Topic[OrderExecutedEvent]("orders")


def _create_market_change_topic() -> Topic:
    """Create the MARKET_CHANGE topic."""
    from polytrader.types import MarketChangeEvent

    return Topic[MarketChangeEvent]("market_change")


def _create_system_lifecycle_topic() -> Topic:
    """Create the SYSTEM_LIFECYCLE topic.

    This topic is used for system lifecycle events such as
    SystemStartedEvent, SystemStoppedEvent, and ConfigLoadedEvent.
    """
    from polytrader.events.types import Event

    return Topic[Event]("system_lifecycle")


def get_market_data_topic() -> Topic:
    """Get the MARKET_DATA topic (singleton)."""
    global _market_data_topic
    if _market_data_topic is None:
        _market_data_topic = _create_market_data_topic()
    return _market_data_topic


def get_proposals_topic() -> Topic:
    """Get the PROPOSALS topic (singleton)."""
    global _proposals_topic
    if _proposals_topic is None:
        _proposals_topic = _create_proposals_topic()
    return _proposals_topic


def get_orders_topic() -> Topic:
    """Get the ORDERS topic (singleton)."""
    global _orders_topic
    if _orders_topic is None:
        _orders_topic = _create_orders_topic()
    return _orders_topic


def get_market_change_topic() -> Topic:
    """Get the MARKET_CHANGE topic (singleton)."""
    global _market_change_topic
    if _market_change_topic is None:
        _market_change_topic = _create_market_change_topic()
    return _market_change_topic


def get_system_lifecycle_topic() -> Topic:
    """Get the SYSTEM_LIFECYCLE topic (singleton)."""
    global _system_lifecycle_topic
    if _system_lifecycle_topic is None:
        _system_lifecycle_topic = _create_system_lifecycle_topic()
    return _system_lifecycle_topic


def _create_risk_checks_topic() -> Topic:
    """Create the RISK_CHECKS topic."""
    from polytrader.events.types import RiskCheckEvent

    return Topic[RiskCheckEvent]("risk_checks")


def get_risk_checks_topic() -> Topic:
    """Get the RISK_CHECKS topic (singleton)."""
    global _risk_checks_topic
    if _risk_checks_topic is None:
        _risk_checks_topic = _create_risk_checks_topic()
    return _risk_checks_topic


def _create_approved_proposals_topic() -> Topic:
    """Create the APPROVED_PROPOSALS topic."""
    from polytrader.types import OrderIntentEvent

    return Topic[OrderIntentEvent]("approved_proposals")


def get_approved_proposals_topic() -> Topic:
    """Get the APPROVED_PROPOSALS topic (singleton)."""
    global _approved_proposals_topic
    if _approved_proposals_topic is None:
        _approved_proposals_topic = _create_approved_proposals_topic()
    return _approved_proposals_topic


def _create_order_created_topic() -> Topic:
    """Create the ORDER_CREATED topic."""
    from polytrader.events.types import OrderCreatedEvent

    return Topic[OrderCreatedEvent]("order_created")


def get_order_created_topic() -> Topic:
    """Get the ORDER_CREATED topic (singleton)."""
    global _order_created_topic
    if _order_created_topic is None:
        _order_created_topic = _create_order_created_topic()
    return _order_created_topic


def _create_order_submitted_topic() -> Topic:
    """Create the ORDER_SUBMITTED topic."""
    from polytrader.events.types import OrderSubmittedEvent

    return Topic[OrderSubmittedEvent]("order_submitted")


def get_order_submitted_topic() -> Topic:
    """Get the ORDER_SUBMITTED topic (singleton)."""
    global _order_submitted_topic
    if _order_submitted_topic is None:
        _order_submitted_topic = _create_order_submitted_topic()
    return _order_submitted_topic


def _create_order_acks_topic() -> Topic:
    """Create the ORDER_ACKS topic."""
    from polytrader.events.types import OrderAckEvent

    return Topic[OrderAckEvent]("order_acks")


def get_order_acks_topic() -> Topic:
    """Get the ORDER_ACKS topic (singleton)."""
    global _order_acks_topic
    if _order_acks_topic is None:
        _order_acks_topic = _create_order_acks_topic()
    return _order_acks_topic


def _create_order_rejects_topic() -> Topic:
    """Create the ORDER_REJECTS topic."""
    from polytrader.events.types import OrderRejectedEvent

    return Topic[OrderRejectedEvent]("order_rejects")


def get_order_rejects_topic() -> Topic:
    """Get the ORDER_REJECTS topic (singleton)."""
    global _order_rejects_topic
    if _order_rejects_topic is None:
        _order_rejects_topic = _create_order_rejects_topic()
    return _order_rejects_topic


def _create_fills_topic() -> Topic:
    """Create the FILLS topic."""
    from polytrader.events.types import FillEvent

    return Topic[FillEvent]("fills")


def get_fills_topic() -> Topic:
    """Get the FILLS topic (singleton)."""
    global _fills_topic
    if _fills_topic is None:
        _fills_topic = _create_fills_topic()
    return _fills_topic


def _create_order_cancels_topic() -> Topic:
    """Create the ORDER_CANCELS topic."""
    from polytrader.events.types import OrderCanceledEvent

    return Topic[OrderCanceledEvent]("order_cancels")


def get_order_cancels_topic() -> Topic:
    """Get the ORDER_CANCELS topic (singleton)."""
    global _order_cancels_topic
    if _order_cancels_topic is None:
        _order_cancels_topic = _create_order_cancels_topic()
    return _order_cancels_topic


def __getattr__(name: str) -> Topic:
    """Lazily initialize topic constants on first access.

    This defers topic initialization until after all modules are fully loaded,
    breaking the circular import between polytrader.types and polytrader.events.topics.

    Args:
        name: Name of the topic constant to retrieve

    Returns:
        The requested Topic instance

    Raises:
        AttributeError: If the requested topic name is not recognized
    """
    if name == "MARKET_DATA":
        return get_market_data_topic()
    elif name == "PROPOSALS":
        return get_proposals_topic()
    elif name == "ORDERS":
        return get_orders_topic()
    elif name == "MARKET_CHANGE":
        return get_market_change_topic()
    elif name == "SYSTEM_LIFECYCLE":
        return get_system_lifecycle_topic()
    elif name == "RISK_CHECKS":
        return get_risk_checks_topic()
    elif name == "APPROVED_PROPOSALS":
        return get_approved_proposals_topic()
    elif name == "ORDER_CREATED":
        return get_order_created_topic()
    elif name == "ORDER_SUBMITTED":
        return get_order_submitted_topic()
    elif name == "ORDER_ACKS":
        return get_order_acks_topic()
    elif name == "ORDER_REJECTS":
        return get_order_rejects_topic()
    elif name == "FILLS":
        return get_fills_topic()
    elif name == "ORDER_CANCELS":
        return get_order_cancels_topic()
    else:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
