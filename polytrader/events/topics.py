"""Topic constants for event bus."""

from polytrader.events.bus import Topic

# Lazy initialization to avoid circular imports
_market_data_topic: Topic | None = None
_proposals_topic: Topic | None = None
_orders_topic: Topic | None = None
_market_change_topic: Topic | None = None
_system_lifecycle_topic: Topic | None = None


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


# Topic constants
MARKET_DATA = get_market_data_topic()
PROPOSALS = get_proposals_topic()
ORDERS = get_orders_topic()
MARKET_CHANGE = get_market_change_topic()
SYSTEM_LIFECYCLE = get_system_lifecycle_topic()
