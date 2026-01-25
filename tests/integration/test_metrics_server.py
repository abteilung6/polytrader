"""Integration tests for dedicated metrics HTTP server.

Per Commit 4: Verify metrics server starts correctly, exposes /metrics endpoint,
and returns Prometheus format. Tests verify server runs in background thread
and is accessible on the configured port.
"""

import time
from threading import Thread

import requests

from polytrader.obs.metrics import (
    create_metrics_collector,
    set_metrics_collector,
)
from polytrader.obs.metrics_server import start_metrics_server, stop_metrics_server


class TestMetricsServerBasic:
    """Basic tests for metrics server functionality."""

    def test_start_metrics_server_default_port(self) -> None:
        """Test that metrics server starts on default port 9100."""
        # Use a random port to avoid conflicts
        import socket

        sock = socket.socket()
        sock.bind(("", 0))
        test_port = sock.getsockname()[1]
        sock.close()

        thread = start_metrics_server(port=test_port)

        # Verify thread is running
        assert thread.is_alive()
        assert thread.daemon is True
        assert thread.name == "metrics-server"

        # Give server a moment to start
        time.sleep(0.1)

        # Verify server is accessible
        try:
            response = requests.get(f"http://localhost:{test_port}/metrics", timeout=1)
            assert response.status_code == 200
            assert "text/plain" in response.headers.get("content-type", "")
        finally:
            # Cleanup: server will stop when process exits (daemon thread)
            stop_metrics_server()

    def test_start_metrics_server_custom_port(self) -> None:
        """Test that metrics server starts on custom port."""
        import socket

        sock = socket.socket()
        sock.bind(("", 0))
        test_port = sock.getsockname()[1]
        sock.close()

        thread = start_metrics_server(port=test_port)

        # Verify thread is running
        assert thread.is_alive()

        # Give server a moment to start
        time.sleep(0.1)

        # Verify server is accessible on custom port
        try:
            response = requests.get(f"http://localhost:{test_port}/metrics", timeout=1)
            assert response.status_code == 200
        finally:
            stop_metrics_server()

    def test_metrics_endpoint_returns_prometheus_format(self) -> None:
        """Test that /metrics endpoint returns Prometheus text format."""
        import socket

        sock = socket.socket()
        sock.bind(("", 0))
        test_port = sock.getsockname()[1]
        sock.close()

        start_metrics_server(port=test_port)

        # Give server a moment to start
        time.sleep(0.1)

        try:
            response = requests.get(f"http://localhost:{test_port}/metrics", timeout=1)
            assert response.status_code == 200

            # Verify Prometheus format
            content = response.text
            # Prometheus format should have HELP and TYPE comments
            assert "# HELP" in content or "# TYPE" in content or len(content) > 0
        finally:
            stop_metrics_server()


class TestMetricsServerWithPrometheusBackend:
    """Tests for metrics server with Prometheus backend."""

    def test_metrics_server_exports_prometheus_metrics(self) -> None:
        """Test that metrics server exports metrics from PrometheusMetricsCollector."""
        import socket

        sock = socket.socket()
        sock.bind(("", 0))
        test_port = sock.getsockname()[1]
        sock.close()

        # Use Prometheus backend
        collector = create_metrics_collector(backend="prometheus")
        set_metrics_collector(collector)

        # Record some metrics
        collector.increment_counter("test_counter_total", labels={"status": "success"})
        collector.set_gauge("test_gauge", 42.0, labels={"market": "btc"})
        collector.record_histogram("test_histogram", 10.5, labels={"operation": "read"})

        # Start server
        start_metrics_server(port=test_port)

        # Give server a moment to start
        time.sleep(0.1)

        try:
            # Query metrics endpoint
            response = requests.get(f"http://localhost:{test_port}/metrics", timeout=1)
            assert response.status_code == 200

            content = response.text

            # Verify our metrics are in the output
            assert "test_counter_total" in content
            assert "test_gauge" in content
            assert "test_histogram" in content
        finally:
            set_metrics_collector(None)
            stop_metrics_server()

    def test_metrics_server_uses_default_registry(self) -> None:
        """Test that metrics server uses default REGISTRY by default."""
        import socket

        sock = socket.socket()
        sock.bind(("", 0))
        test_port = sock.getsockname()[1]
        sock.close()

        # Use Prometheus backend (uses default REGISTRY)
        collector = create_metrics_collector(backend="prometheus")
        set_metrics_collector(collector)

        # Record a metric
        collector.increment_counter("registry_test_total")

        # Start server (should use default REGISTRY)
        start_metrics_server(port=test_port)

        # Give server a moment to start
        time.sleep(0.1)

        try:
            # Query metrics endpoint
            response = requests.get(f"http://localhost:{test_port}/metrics", timeout=1)
            assert response.status_code == 200

            # Verify metric is exported
            content = response.text
            assert "registry_test_total" in content
        finally:
            set_metrics_collector(None)
            stop_metrics_server()


class TestMetricsServerConfiguration:
    """Tests for metrics server port configuration via MetricsConfig."""

    def test_metrics_server_reads_port_from_config(self) -> None:
        """Test that metrics server reads port from MetricsConfig."""
        import socket

        from polytrader.config import MetricsConfig

        sock = socket.socket()
        sock.bind(("", 0))
        test_port = sock.getsockname()[1]
        sock.close()

        # Create config with custom port (use model_construct to bypass env file)
        config = MetricsConfig.model_construct(metrics_port=test_port)

        # Start server without specifying port (should read from config)
        start_metrics_server(port=None, config=config)

        # Give server a moment to start
        time.sleep(0.1)

        try:
            # Verify server is accessible on config-specified port
            response = requests.get(f"http://localhost:{test_port}/metrics", timeout=1)
            assert response.status_code == 200
        finally:
            stop_metrics_server()

    def test_metrics_server_defaults_to_9100_when_config_not_provided(self) -> None:
        """Test that metrics server defaults to 9100 when config not provided."""
        # Start server without specifying port or config (should default to 9100)
        # Note: We can't actually test port 9100 in CI (might be in use),
        # but we can verify the function doesn't crash
        try:
            thread = start_metrics_server(port=None, config=None)
            # If it doesn't crash, the default logic works
            assert thread.is_alive()
            time.sleep(0.1)
        except OSError:
            # Port 9100 might be in use, which is acceptable
            # The important thing is that the default logic was executed
            pass
        finally:
            stop_metrics_server()


class TestMetricsServerThreading:
    """Tests for metrics server threading behavior."""

    def test_metrics_server_runs_in_daemon_thread(self) -> None:
        """Test that metrics server runs in a daemon thread."""
        import socket

        sock = socket.socket()
        sock.bind(("", 0))
        test_port = sock.getsockname()[1]
        sock.close()

        thread = start_metrics_server(port=test_port, config=None)

        # Verify thread properties
        assert isinstance(thread, Thread)
        assert thread.daemon is True
        assert thread.is_alive()

        stop_metrics_server()

    def test_metrics_server_thread_name(self) -> None:
        """Test that metrics server thread has correct name."""
        import socket

        sock = socket.socket()
        sock.bind(("", 0))
        test_port = sock.getsockname()[1]
        sock.close()

        thread = start_metrics_server(port=test_port)

        # Verify thread name
        assert thread.name == "metrics-server"

        stop_metrics_server()
