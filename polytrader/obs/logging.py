"""Structured logging helper utilities per observability.mdc §2, §3.

Per observability.mdc §2: Every log line must include correlation_id when applicable.
Per observability.mdc §3: Structured logging with mandatory fields.

These helper functions reduce boilerplate and ensure consistency across modules.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from loguru import Logger

    from polytrader.oms.models import Order


def bind_correlation_context(logger: Logger, correlation_id: str, **kwargs: Any) -> Logger:
    """Bind correlation_id and common fields to logger context.

    Per observability.mdc §2: Every log line must include correlation_id when applicable.
    Per observability.mdc §3: Structured logging with mandatory fields.

    This helper ensures correlation_id is always present and allows additional
    common fields to be bound (market_slug, outcome, event_type, etc.).

    Args:
        logger: Loguru logger instance
        correlation_id: Correlation ID for tracing decision → actions
        **kwargs: Additional fields to bind (e.g., market_slug, outcome, event_type, run_id)

    Returns:
        Bound logger instance with correlation_id and additional fields

    Example:
        >>> from polytrader.logging_config import logger
        >>> log_ctx = bind_correlation_context(
        ...     logger,
        ...     correlation_id="abc123",
        ...     market_slug="btc-updown-15m",
        ...     event_type="SignalEvent",
        ... )
        >>> log_ctx.info("Signal generated")
    """
    context = {"correlation_id": correlation_id}
    context.update(kwargs)
    return logger.bind(**context)


def bind_order_context(logger: Logger, order: Order, **kwargs: Any) -> Logger:
    """Bind order-related fields to logger context.

    Per observability.mdc §2: Orders have order_id, client_order_id, venue_order_id.
    Per observability.mdc §3: Mandatory fields include correlation_id, order_id,
    client_order_id, venue_order_id, market, event_type.

    This helper extracts all order-related fields and binds them to the logger,
    ensuring consistent structured logging for order lifecycle events.

    Args:
        logger: Loguru logger instance
        order: Order instance to extract fields from
        **kwargs: Additional fields to bind (e.g., event_type, latency_ms, error_class)

    Returns:
        Bound logger instance with order-related fields

    Example:
        >>> from polytrader.logging_config import logger
        >>> log_ctx = bind_order_context(
        ...     logger,
        ...     order,
        ...     event_type="OrderSubmitted",
        ...     latency_ms=5.0,
        ... )
        >>> log_ctx.info("Order submitted to execution")
    """
    context = {
        "correlation_id": order.correlation_id,
        "order_id": order.order_id,
        "client_order_id": order.client_order_id,
        "venue_order_id": order.venue_order_id,
        "market_slug": order.market_slug,
        "outcome": order.outcome,
        "side": order.side,
    }
    context.update(kwargs)
    return logger.bind(**context)


def bind_strategy_context(
    logger: Logger, strategy_id: str, correlation_id: str | None = None, **kwargs: Any
) -> Logger:
    """Bind strategy-related fields to logger context.

    Per observability.mdc §2: Strategy logs should include strategy_id and correlation_id.
    Per observability.mdc §3: Mandatory fields include strategy_id, correlation_id,
    market, event_type, latency_ms (when applicable).

    This helper ensures strategy-related fields are consistently bound to logger context.

    Args:
        logger: Loguru logger instance
        strategy_id: Strategy identifier (e.g., "simple_threshold")
        correlation_id: Optional correlation ID (for tracing decision → actions)
        **kwargs: Additional fields to bind (e.g., market_slug, event_type, latency_ms)

    Returns:
        Bound logger instance with strategy-related fields

    Example:
        >>> from polytrader.logging_config import logger
        >>> log_ctx = bind_strategy_context(
        ...     logger,
        ...     strategy_id="simple_threshold",
        ...     correlation_id="abc123",
        ...     market_slug="btc-updown-15m",
        ...     event_type="StrategyEval",
        ...     latency_ms=2.5,
        ... )
        >>> log_ctx.info("Strategy evaluation completed")
    """
    context: dict[str, Any] = {"strategy_id": strategy_id}
    if correlation_id:
        context["correlation_id"] = correlation_id
    context.update(kwargs)
    return logger.bind(**context)
