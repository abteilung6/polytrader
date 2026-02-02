"""Dedicated HTTP server for Prometheus metrics scraping.

Per Commit 4: Separate metrics server on port 9100, isolated from
FastAPI control API on port 8000. This maintains clean separation:
- Control API (:8000) - public/operator-facing
- Metrics server (:9100) - private, Prometheus scraping only

Per architecture.mdc: Clean separation of concerns, minimal complexity.
"""

import threading
from typing import TYPE_CHECKING

from prometheus_client import REGISTRY, start_http_server

from polytrader.config import MetricsConfig

if TYPE_CHECKING:
    from prometheus_client.registry import CollectorRegistry

# Global reference to metrics server thread (for cleanup)
_metrics_server_thread: threading.Thread | None = None


def start_metrics_server(
    port: int | None = None,
    registry: "CollectorRegistry | None" = None,
    config: MetricsConfig | None = None,
) -> threading.Thread:
    """Start Prometheus metrics HTTP server in background thread.

    Args:
        port: Port to listen on (default: from config or 9100)
        registry: Prometheus CollectorRegistry to use (default: REGISTRY)
        config: MetricsConfig instance. If None, loads from environment.

    Returns:
        Thread running the metrics server (daemon thread)

    Raises:
        OSError: If port is already in use
        ValueError: If port is invalid

    Note:
        The server runs in a daemon thread, so it will automatically
        stop when the main process exits. The thread is stored globally
        for potential cleanup if needed.
    """
    global _metrics_server_thread

    # Get port from config/env var or use default
    if port is None:
        if config is None:
            config = MetricsConfig()
        port = config.metrics_port

    # Use provided registry or default REGISTRY
    # Note: If using PrometheusMetricsCollector with custom registry,
    # the caller should pass that registry here
    metrics_registry = registry or REGISTRY

    # prometheus_client.start_http_server starts its own daemon thread and returns
    # (server, thread). We return that thread so callers can assert thread.is_alive().
    _server, thread = start_http_server(port, registry=metrics_registry)
    thread.name = "metrics-server"

    # Store reference for potential cleanup
    _metrics_server_thread = thread

    return thread


def stop_metrics_server() -> None:
    """Stop the metrics server (if running).

    Note:
        Since the server runs in a daemon thread, it will automatically
        stop when the main process exits. This function is provided for
        explicit cleanup if needed, but is typically not required.
    """
    global _metrics_server_thread
    # prometheus_client.start_http_server() doesn't provide a clean shutdown API
    # The daemon thread will stop when the process exits
    # This is a no-op for now, but provides a hook for future cleanup if needed
    _metrics_server_thread = None
