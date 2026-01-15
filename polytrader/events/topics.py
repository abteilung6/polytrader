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
_submit_order_commands_topic: Topic | None = None
_cancel_order_commands_topic: Topic | None = None
_execution_requests_topic: Topic | None = None
_execution_responses_topic: Topic | None = None
_execution_errors_topic: Topic | None = None
_market_discovery_topic: Topic | None = None
_signals_topic: Topic | None = None
_targets_topic: Topic | None = None
_user_stream_acks_topic: Topic | None = None
_user_stream_rejects_topic: Topic | None = None
_user_stream_fills_topic: Topic | None = None
_user_stream_cancels_topic: Topic | None = None
_reconcile_topic: Topic | None = None
_circuit_breaker_topic: Topic | None = None
_position_updates_topic: Topic | None = None
_pnl_updates_topic: Topic | None = None
_cancel_requested_topic: Topic | None = None
_venue_connected_topic: Topic | None = None
_venue_disconnected_topic: Topic | None = None


def _create_market_data_topic() -> Topic:
    """Create the MARKET_DATA topic."""
    from polytrader.events.types import MarketDataEvent

    return Topic[MarketDataEvent]("market_data")


def _create_proposals_topic() -> Topic:
    """Create the PROPOSALS topic."""
    from polytrader.events.types import OrderIntentEvent

    return Topic[OrderIntentEvent]("proposals")


def _create_orders_topic() -> Topic:
    """Create the ORDERS topic."""
    from polytrader.events.types import OrderExecutedEvent

    return Topic[OrderExecutedEvent]("orders")


def _create_market_change_topic() -> Topic:
    """Create the MARKET_CHANGE topic."""
    from polytrader.events.types import MarketChangeEvent

    return Topic[MarketChangeEvent]("market_change")


def _create_system_lifecycle_topic() -> Topic:
    """Create the SYSTEM_LIFECYCLE topic.

    This topic is used for system lifecycle events such as
    SystemStartedEvent, SystemStoppedEvent, and ConfigLoadedEvent.
    """
    from polytrader.events.types import Event

    return Topic[Event]("system_lifecycle")


def _create_market_discovery_topic() -> Topic:
    """Create the MARKET_DISCOVERY topic."""
    from polytrader.events.types import MarketDiscoveryEvent

    return Topic[MarketDiscoveryEvent]("market_discovery")


def _create_signals_topic() -> Topic:
    """Create the SIGNALS topic."""
    from polytrader.events.types import SignalEvent

    return Topic[SignalEvent]("signals")


def _create_targets_topic() -> Topic:
    """Create the TARGETS topic."""
    from polytrader.events.types import TargetEvent

    return Topic[TargetEvent]("targets")


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
    from polytrader.events.types import OrderIntentEvent

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


def _create_submit_order_commands_topic() -> Topic:
    """Create the SUBMIT_ORDER_COMMANDS topic."""
    from polytrader.oms.commands import SubmitOrderCommand

    return Topic[SubmitOrderCommand]("submit_order_commands")


def get_submit_order_commands_topic() -> Topic:
    """Get the SUBMIT_ORDER_COMMANDS topic (singleton)."""
    global _submit_order_commands_topic
    if _submit_order_commands_topic is None:
        _submit_order_commands_topic = _create_submit_order_commands_topic()
    return _submit_order_commands_topic


def _create_cancel_order_commands_topic() -> Topic:
    """Create the CANCEL_ORDER_COMMANDS topic."""
    from polytrader.oms.commands import CancelOrderCommand

    return Topic[CancelOrderCommand]("cancel_order_commands")


def get_cancel_order_commands_topic() -> Topic:
    """Get the CANCEL_ORDER_COMMANDS topic (singleton)."""
    global _cancel_order_commands_topic
    if _cancel_order_commands_topic is None:
        _cancel_order_commands_topic = _create_cancel_order_commands_topic()
    return _cancel_order_commands_topic


def _create_execution_requests_topic() -> Topic:
    """Create the EXECUTION_REQUESTS topic."""
    from polytrader.events.types import ExecutionRequestEvent

    return Topic[ExecutionRequestEvent]("execution_requests")


def get_execution_requests_topic() -> Topic:
    """Get the EXECUTION_REQUESTS topic (singleton)."""
    global _execution_requests_topic
    if _execution_requests_topic is None:
        _execution_requests_topic = _create_execution_requests_topic()
    return _execution_requests_topic


def _create_execution_responses_topic() -> Topic:
    """Create the EXECUTION_RESPONSES topic."""
    from polytrader.events.types import ExecutionResponseEvent

    return Topic[ExecutionResponseEvent]("execution_responses")


def get_execution_responses_topic() -> Topic:
    """Get the EXECUTION_RESPONSES topic (singleton)."""
    global _execution_responses_topic
    if _execution_responses_topic is None:
        _execution_responses_topic = _create_execution_responses_topic()
    return _execution_responses_topic


def _create_execution_errors_topic() -> Topic:
    """Create the EXECUTION_ERRORS topic."""
    from polytrader.events.types import ExecutionErrorEvent

    return Topic[ExecutionErrorEvent]("execution_errors")


def get_execution_errors_topic() -> Topic:
    """Get the EXECUTION_ERRORS topic (singleton)."""
    global _execution_errors_topic
    if _execution_errors_topic is None:
        _execution_errors_topic = _create_execution_errors_topic()
    return _execution_errors_topic


def get_market_discovery_topic() -> Topic:
    """Get the MARKET_DISCOVERY topic (singleton)."""
    global _market_discovery_topic
    if _market_discovery_topic is None:
        _market_discovery_topic = _create_market_discovery_topic()
    return _market_discovery_topic


def get_signals_topic() -> Topic:
    """Get the SIGNALS topic (singleton)."""
    global _signals_topic
    if _signals_topic is None:
        _signals_topic = _create_signals_topic()
    return _signals_topic


def get_targets_topic() -> Topic:
    """Get the TARGETS topic (singleton)."""
    global _targets_topic
    if _targets_topic is None:
        _targets_topic = _create_targets_topic()
    return _targets_topic


def _create_user_stream_acks_topic() -> Topic:
    """Create the USER_STREAM_ACKS topic."""
    from polytrader.adapters.polymarket.models import CanonicalOrderAck

    return Topic[CanonicalOrderAck]("user_stream_acks")


def get_user_stream_acks_topic() -> Topic:
    """Get the USER_STREAM_ACKS topic (singleton)."""
    global _user_stream_acks_topic
    if _user_stream_acks_topic is None:
        _user_stream_acks_topic = _create_user_stream_acks_topic()
    return _user_stream_acks_topic


def _create_user_stream_rejects_topic() -> Topic:
    """Create the USER_STREAM_REJECTS topic."""
    from polytrader.adapters.polymarket.models import CanonicalOrderReject

    return Topic[CanonicalOrderReject]("user_stream_rejects")


def get_user_stream_rejects_topic() -> Topic:
    """Get the USER_STREAM_REJECTS topic (singleton)."""
    global _user_stream_rejects_topic
    if _user_stream_rejects_topic is None:
        _user_stream_rejects_topic = _create_user_stream_rejects_topic()
    return _user_stream_rejects_topic


def _create_user_stream_fills_topic() -> Topic:
    """Create the USER_STREAM_FILLS topic."""
    from polytrader.adapters.polymarket.models import CanonicalFill

    return Topic[CanonicalFill]("user_stream_fills")


def get_user_stream_fills_topic() -> Topic:
    """Get the USER_STREAM_FILLS topic (singleton)."""
    global _user_stream_fills_topic
    if _user_stream_fills_topic is None:
        _user_stream_fills_topic = _create_user_stream_fills_topic()
    return _user_stream_fills_topic


def _create_user_stream_cancels_topic() -> Topic:
    """Create the USER_STREAM_CANCELS topic."""
    from polytrader.adapters.polymarket.models import CanonicalCancel

    return Topic[CanonicalCancel]("user_stream_cancels")


def get_user_stream_cancels_topic() -> Topic:
    """Get the USER_STREAM_CANCELS topic (singleton)."""
    global _user_stream_cancels_topic
    if _user_stream_cancels_topic is None:
        _user_stream_cancels_topic = _create_user_stream_cancels_topic()
    return _user_stream_cancels_topic


def _create_reconcile_topic() -> Topic:
    """Create the RECONCILE topic."""
    from polytrader.events.types import ReconcileEvent

    return Topic[ReconcileEvent]("reconcile")


def get_reconcile_topic() -> Topic:
    """Get the RECONCILE topic (singleton)."""
    global _reconcile_topic
    if _reconcile_topic is None:
        _reconcile_topic = _create_reconcile_topic()
    return _reconcile_topic


def _create_circuit_breaker_topic() -> Topic:
    """Create the CIRCUIT_BREAKER topic."""
    from polytrader.events.types import CircuitBreakerEvent

    return Topic[CircuitBreakerEvent]("circuit_breaker")


def get_circuit_breaker_topic() -> Topic:
    """Get the CIRCUIT_BREAKER topic (singleton)."""
    global _circuit_breaker_topic
    if _circuit_breaker_topic is None:
        _circuit_breaker_topic = _create_circuit_breaker_topic()
    return _circuit_breaker_topic


def _create_position_updates_topic() -> Topic:
    """Create the POSITION_UPDATES topic."""
    from polytrader.events.types import PositionUpdatedEvent

    return Topic[PositionUpdatedEvent]("position_updates")


def get_position_updates_topic() -> Topic:
    """Get the POSITION_UPDATES topic (singleton)."""
    global _position_updates_topic
    if _position_updates_topic is None:
        _position_updates_topic = _create_position_updates_topic()
    return _position_updates_topic


def _create_pnl_updates_topic() -> Topic:
    """Create the PNL_UPDATES topic."""
    from polytrader.events.types import PnLEvent

    return Topic[PnLEvent]("pnl_updates")


def get_pnl_updates_topic() -> Topic:
    """Get the PNL_UPDATES topic (singleton)."""
    global _pnl_updates_topic
    if _pnl_updates_topic is None:
        _pnl_updates_topic = _create_pnl_updates_topic()
    return _pnl_updates_topic


def _create_cancel_requested_topic() -> Topic:
    """Create the CANCEL_REQUESTED topic."""
    from polytrader.events.types import CancelRequestedEvent

    return Topic[CancelRequestedEvent]("cancel_requested")


def get_cancel_requested_topic() -> Topic:
    """Get the CANCEL_REQUESTED topic (singleton)."""
    global _cancel_requested_topic
    if _cancel_requested_topic is None:
        _cancel_requested_topic = _create_cancel_requested_topic()
    return _cancel_requested_topic


def _create_venue_connected_topic() -> Topic:
    """Create the VENUE_CONNECTED topic."""
    from polytrader.events.types import VenueConnectedEvent

    return Topic[VenueConnectedEvent]("venue_connected")


def get_venue_connected_topic() -> Topic:
    """Get the VENUE_CONNECTED topic (singleton)."""
    global _venue_connected_topic
    if _venue_connected_topic is None:
        _venue_connected_topic = _create_venue_connected_topic()
    return _venue_connected_topic


def _create_venue_disconnected_topic() -> Topic:
    """Create the VENUE_DISCONNECTED topic."""
    from polytrader.events.types import VenueDisconnectedEvent

    return Topic[VenueDisconnectedEvent]("venue_disconnected")


def get_venue_disconnected_topic() -> Topic:
    """Get the VENUE_DISCONNECTED topic (singleton)."""
    global _venue_disconnected_topic
    if _venue_disconnected_topic is None:
        _venue_disconnected_topic = _create_venue_disconnected_topic()
    return _venue_disconnected_topic


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
    elif name == "SUBMIT_ORDER_COMMANDS":
        return get_submit_order_commands_topic()
    elif name == "CANCEL_ORDER_COMMANDS":
        return get_cancel_order_commands_topic()
    elif name == "EXECUTION_REQUESTS":
        return get_execution_requests_topic()
    elif name == "EXECUTION_RESPONSES":
        return get_execution_responses_topic()
    elif name == "EXECUTION_ERRORS":
        return get_execution_errors_topic()
    elif name == "MARKET_DISCOVERY":
        return get_market_discovery_topic()
    elif name == "SIGNALS":
        return get_signals_topic()
    elif name == "TARGETS":
        return get_targets_topic()
    elif name == "USER_STREAM_ACKS":
        return get_user_stream_acks_topic()
    elif name == "USER_STREAM_REJECTS":
        return get_user_stream_rejects_topic()
    elif name == "USER_STREAM_FILLS":
        return get_user_stream_fills_topic()
    elif name == "USER_STREAM_CANCELS":
        return get_user_stream_cancels_topic()
    elif name == "RECONCILE":
        return get_reconcile_topic()
    elif name == "CIRCUIT_BREAKER":
        return get_circuit_breaker_topic()
    elif name == "POSITION_UPDATES":
        return get_position_updates_topic()
    elif name == "PNL_UPDATES":
        return get_pnl_updates_topic()
    elif name == "CANCEL_REQUESTED":
        return get_cancel_requested_topic()
    elif name == "VENUE_CONNECTED":
        return get_venue_connected_topic()
    elif name == "VENUE_DISCONNECTED":
        return get_venue_disconnected_topic()
    else:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
