"""OMS metrics collection per observability.mdc §4.

This module provides functions for recording OMS-related metrics:
- Order lifecycle metrics (created, submitted, acked, rejected, cancelled, filled)
- Latency metrics (submit, ack, fill latencies)
- State metrics (orders_live, orders_by_state)
- Error metrics (invalid transitions, idempotency hits)
"""

from collections import defaultdict

from polytrader.obs.metrics import get_metrics_collector
from polytrader.oms.models import Order, OrderState
from polytrader.oms.store import IOrderStore


def record_order_created(order: Order) -> None:
    """Record order creation metric.

    Per observability.mdc §4: Track orders_created_total.

    Args:
        order: Created order instance
    """
    metrics = get_metrics_collector()
    metrics.increment_counter(
        "orders_created_total",
        labels={
            "market_slug": order.market_slug,
            "outcome": order.outcome,
            "side": order.side,
        },
    )


def record_order_submitted(order: Order, latency_ms: float) -> None:
    """Record order submission metric.

    Per observability.mdc §4: Track orders_submitted_total and submit_latency_ms.

    Args:
        order: Submitted order instance
        latency_ms: Latency from creation to submission (milliseconds)
    """
    metrics = get_metrics_collector()
    metrics.increment_counter(
        "orders_submitted_total",
        labels={
            "market_slug": order.market_slug,
            "outcome": order.outcome,
            "side": order.side,
        },
    )
    metrics.record_histogram(
        "submit_latency_ms",
        latency_ms,
        labels={
            "market_slug": order.market_slug,
            "outcome": order.outcome,
            "side": order.side,
        },
    )


def record_order_acked(order: Order, latency_ms: float) -> None:
    """Record order acknowledgment metric.

    Per observability.mdc §4: Track orders_acked_total and ack_latency_ms.

    Args:
        order: Acknowledged order instance
        latency_ms: Latency from submission to acknowledgment (milliseconds)
    """
    metrics = get_metrics_collector()
    metrics.increment_counter(
        "orders_acked_total",
        labels={
            "market_slug": order.market_slug,
            "outcome": order.outcome,
            "side": order.side,
        },
    )
    metrics.record_histogram(
        "ack_latency_ms",
        latency_ms,
        labels={
            "market_slug": order.market_slug,
            "outcome": order.outcome,
            "side": order.side,
        },
    )


def record_order_rejected(order: Order, reason: str) -> None:
    """Record order rejection metric.

    Per observability.mdc §4: Track rejects_total.

    Args:
        order: Rejected order instance
        reason: Rejection reason
    """
    metrics = get_metrics_collector()
    metrics.increment_counter(
        "rejects_total",
        labels={
            "market_slug": order.market_slug,
            "outcome": order.outcome,
            "side": order.side,
            "reason": reason,
        },
    )


def record_order_cancelled(order: Order, reason: str | None) -> None:
    """Record order cancellation metric.

    Per observability.mdc §4: Track cancels_total.

    Args:
        order: Cancelled order instance
        reason: Cancellation reason (if available)
    """
    metrics = get_metrics_collector()
    metrics.increment_counter(
        "cancels_total",
        labels={
            "market_slug": order.market_slug,
            "outcome": order.outcome,
            "side": order.side,
            "reason": reason or "unknown",
        },
    )


def record_fill(order: Order, latency_ms: float | None = None) -> None:
    """Record fill metric.

    Per observability.mdc §4: Track fills_total and fill_latency_ms.

    Args:
        order: Order that received a fill
        latency_ms: Latency from ack to first fill (milliseconds), if available
    """
    metrics = get_metrics_collector()
    metrics.increment_counter(
        "fills_total",
        labels={
            "market_slug": order.market_slug,
            "outcome": order.outcome,
            "side": order.side,
        },
    )
    if latency_ms is not None:
        metrics.record_histogram(
            "fill_latency_ms",
            latency_ms,
            labels={
                "market_slug": order.market_slug,
                "outcome": order.outcome,
                "side": order.side,
            },
        )


def record_invalid_transition(order: Order, from_state: OrderState, to_state: OrderState) -> None:
    """Record invalid FSM transition attempt.

    Args:
        order: Order that attempted invalid transition
        from_state: Source state
        to_state: Target state
    """
    metrics = get_metrics_collector()
    metrics.increment_counter(
        "invalid_transitions_total",
        labels={
            "from_state": from_state.value,
            "to_state": to_state.value,
            "market_slug": order.market_slug,
        },
    )


def record_idempotency_hit(client_order_id: str) -> None:
    """Record duplicate order detection.

    Args:
        client_order_id: Idempotency key that was detected as duplicate
    """
    metrics = get_metrics_collector()
    metrics.increment_counter("idempotency_hits_total")


def update_orders_live_gauge(store: IOrderStore) -> None:
    """Update orders_live and orders_by_state gauges.

    Per observability.mdc §4: Track orders_live gauge.

    Args:
        store: Order store to query for open orders
    """
    metrics = get_metrics_collector()
    open_orders = store.get_open_orders()

    # Update orders_live gauge
    metrics.set_gauge("orders_live", len(open_orders))

    # Update orders_by_state gauge
    state_counts: dict[OrderState, int] = defaultdict(int)
    for order in open_orders:
        state_counts[order.state] += 1

    for state, count in state_counts.items():
        metrics.set_gauge(
            "orders_by_state",
            count,
            labels={"state": state.value},
        )


def record_order_lifetime(order: Order, lifetime_ms: float) -> None:
    """Record order lifetime metric.

    Tracks latency from order creation to terminal state.

    Args:
        order: Order that reached terminal state
        lifetime_ms: Total order lifetime (milliseconds)
    """
    metrics = get_metrics_collector()
    metrics.record_histogram(
        "order_lifetime_ms",
        lifetime_ms,
        labels={
            "market_slug": order.market_slug,
            "outcome": order.outcome,
            "side": order.side,
            "final_state": order.state.value,
        },
    )
