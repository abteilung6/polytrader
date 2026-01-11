"""Supervisor metrics collection per observability.mdc §4.

This module provides functions for recording supervisor-related metrics:
- Service lifecycle metrics (startup time, failures)
- Supervisor state metrics (services running, transitions)
"""

from polytrader.obs.metrics import get_metrics_collector


def record_service_started(
    service_name: str, supervisor_type: str, startup_time_ms: float | None = None
) -> None:
    """Record service started metric.

    Per observability.mdc §4: Track service lifecycle.

    Args:
        service_name: Name of the service (e.g., "PortfolioService")
        supervisor_type: Type of supervisor ("SystemSupervisor" or "MarketSupervisor")
        startup_time_ms: Time taken to start the service (ms)
    """
    metrics = get_metrics_collector()
    metrics.increment_counter(
        "supervisor_service_started_total",
        labels={"service": service_name, "supervisor": supervisor_type},
    )
    if startup_time_ms is not None:
        metrics.record_histogram(
            "supervisor_startup_time_ms",
            startup_time_ms,
            labels={"service": service_name, "supervisor": supervisor_type},
        )


def record_service_stopped(service_name: str, supervisor_type: str) -> None:
    """Record service stopped metric.

    Per observability.mdc §4: Track service lifecycle.

    Args:
        service_name: Name of the service
        supervisor_type: Type of supervisor
    """
    metrics = get_metrics_collector()
    metrics.increment_counter(
        "supervisor_service_stopped_total",
        labels={"service": service_name, "supervisor": supervisor_type},
    )


def record_service_error(
    service_name: str,
    supervisor_type: str,
    error_type: str,
    error_class: str,
) -> None:
    """Record service error metric.

    Per observability.mdc §4: Track service failures.

    Args:
        service_name: Name of the service
        supervisor_type: Type of supervisor
        error_type: Type of error (e.g., "RuntimeError")
        error_class: Error classification ("retryable" or "fatal")
    """
    metrics = get_metrics_collector()
    metrics.increment_counter(
        "supervisor_service_failures_total",
        labels={
            "service": service_name,
            "supervisor": supervisor_type,
            "error_type": error_type,
            "error_class": error_class,
        },
    )


def record_market_transition(supervisor_type: str, old_market: str | None, new_market: str) -> None:
    """Record market transition metric.

    Per observability.mdc §4: Track market transitions.

    Args:
        supervisor_type: Type of supervisor (should be "MarketSupervisor")
        old_market: Previous market slug (None for initial market)
        new_market: New market slug
    """
    metrics = get_metrics_collector()
    metrics.increment_counter(
        "supervisor_market_transitions_total",
        labels={"supervisor": supervisor_type},
    )


def set_services_running(supervisor_type: str, count: int) -> None:
    """Set gauge for number of running services.

    Per observability.mdc §4: Track service state.

    Args:
        supervisor_type: Type of supervisor
        count: Number of running services
    """
    metrics = get_metrics_collector()
    metrics.set_gauge(
        "supervisor_services_running",
        float(count),
        labels={"supervisor": supervisor_type},
    )


def record_supervisor_startup_time(supervisor_type: str, startup_time_ms: float) -> None:
    """Record total supervisor startup time.

    Per observability.mdc §4: Track supervisor performance.

    Args:
        supervisor_type: Type of supervisor
        startup_time_ms: Total startup time in milliseconds
    """
    metrics = get_metrics_collector()
    metrics.record_histogram(
        "supervisor_startup_time_ms",
        startup_time_ms,
        labels={"supervisor": supervisor_type},
    )
