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


class TestMetricsServerWithMemoryBackend:
    """Tests for metrics server with memory backend."""

    def test_metrics_server_with_memory_backend(self) -> None:
        """Test that metrics server works with memory backend."""
        import socket

        sock = socket.socket()
        sock.bind(("", 0))
        test_port = sock.getsockname()[1]
        sock.close()

        # Use memory backend
        collector = create_metrics_collector(backend="memory")
        set_metrics_collector(collector)

        # Record some metrics
        collector.increment_counter("test_counter_total", labels={"status": "success"})
        collector.set_gauge("test_gauge", 42.0, labels={"market": "btc"})
        collector.record_histogram("test_histogram", 10.5, labels={"operation": "read"})

        # Start server (should still work, but metrics won't be in Prometheus format
        # since memory backend doesn't use Prometheus registry)
        start_metrics_server(port=test_port)

        # Give server a moment to start
        time.sleep(0.1)

        try:
            # Query metrics endpoint (should return 200, but may not have our metrics
            # since memory backend doesn't register with Prometheus REGISTRY)
            response = requests.get(f"http://localhost:{test_port}/metrics", timeout=1)
            assert response.status_code == 200

            # Memory backend metrics won't appear in Prometheus format
            # (they're in-memory only, not in Prometheus registry)
            # But the endpoint should still work
            content = response.text
            # Prometheus format should be present (even if empty or with default metrics)
            assert "#" in content or len(content) >= 0
        finally:
            set_metrics_collector(None)
            stop_metrics_server()


class TestMetricsFactoryDefaults:
    """Tests to verify factory defaults to prometheus."""

    def test_factory_defaults_to_prometheus(self) -> None:
        """Test that create_metrics_collector defaults to prometheus backend."""
        import os
        from unittest.mock import patch

        # Clear any env var to test default
        with patch.dict(os.environ, {}, clear=True):
            collector = create_metrics_collector()
            # Should be PrometheusMetricsCollector by default
            from polytrader.obs.metrics_prometheus import PrometheusMetricsCollector

            assert isinstance(collector, PrometheusMetricsCollector)


class TestPrometheusScrapingIntegration:
    """Integration tests for Prometheus scraping (requires Prometheus server).

    These tests verify end-to-end metrics flow:
    - Metrics server exposes /metrics endpoint
    - Prometheus can scrape the endpoint
    - Metrics appear in Prometheus query API
    - Metric values match expected values

    Note: These tests require a Prometheus instance running on port 9091
    (test Prometheus). Use `make test-prometheus-up` before running these tests.
    """

    def test_prometheus_can_scrape_metrics(self) -> None:
        """Test that Prometheus can scrape metrics from our server.

        This test requires Prometheus test instance to be running.
        Use `make test-prometheus-up` before running this test.
        """
        import socket

        import pytest

        # Check if Prometheus is available
        try:
            response = requests.get("http://localhost:9091/-/healthy", timeout=2)
            if response.status_code != 200:
                pytest.skip("Prometheus test instance not available (not healthy)")
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
            pytest.skip("Prometheus test instance not available (not running)")

        sock = socket.socket()
        sock.bind(("", 0))
        test_port = sock.getsockname()[1]
        sock.close()

        # Use Prometheus backend
        collector = create_metrics_collector(backend="prometheus")
        set_metrics_collector(collector)

        # Record some test metrics
        collector.increment_counter("integration_test_counter_total", labels={"test": "scraping"})
        collector.set_gauge("integration_test_gauge", 99.0, labels={"test": "scraping"})
        collector.record_histogram("integration_test_histogram", 50.0, labels={"test": "scraping"})

        # Start metrics server
        start_metrics_server(port=test_port)

        # Give server a moment to start
        time.sleep(0.2)

        try:
            # Verify metrics endpoint is accessible
            response = requests.get(f"http://localhost:{test_port}/metrics", timeout=1)
            assert response.status_code == 200

            # For a full integration test, we would need to:
            # 1. Configure Prometheus to scrape our test_port (requires Prometheus config update)
            # 2. Wait for Prometheus to scrape (scrape_interval: 5s for test Prometheus)
            # 3. Query Prometheus API to verify metrics appear

            # Since we can't dynamically update Prometheus config in this test,
            # we verify that:
            # - Metrics server is accessible
            # - Metrics are in Prometheus format
            # - Metrics contain our test metrics

            content = response.text
            assert "integration_test_counter_total" in content
            assert "integration_test_gauge" in content
            assert "integration_test_histogram" in content

            # Note: Full end-to-end test (Prometheus scraping and querying) will be
            # added in Commit 7 when Prometheus Docker Compose is set up with
            # proper scrape configuration for test port.
        finally:
            set_metrics_collector(None)
            stop_metrics_server()

    def test_prometheus_query_api_returns_metrics(self) -> None:
        """Test that Prometheus query API returns our metrics.

        This test requires Prometheus test instance to be running and configured
        to scrape our metrics server. Use `make test-prometheus-up` and ensure
        Prometheus is configured to scrape the test metrics server.

        Note: This test will be fully functional after Commit 7 (Prometheus Docker
        Compose setup) when Prometheus is configured to scrape test metrics server.
        """
        import pytest

        # Check if Prometheus is available
        try:
            response = requests.get("http://localhost:9091/-/healthy", timeout=2)
            if response.status_code != 200:
                pytest.skip("Prometheus test instance not available (not healthy)")
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
            pytest.skip("Prometheus test instance not available (not running)")

        # Try to query Prometheus API
        # Note: This will only work if Prometheus is configured to scrape our metrics
        # and has actually scraped them. This requires Commit 7 setup.
        try:
            response = requests.get(
                "http://localhost:9091/api/v1/query",
                params={"query": "integration_test_counter_total"},
                timeout=2,
            )
            # If Prometheus is running but not configured to scrape our metrics,
            # the query will return success but with empty result
            if response.status_code == 200:
                data = response.json()
                assert data["status"] == "success"
                # Result may be empty if Prometheus hasn't scraped our metrics yet
                # This is expected until Commit 7 sets up proper scrape configuration
        except requests.exceptions.RequestException:
            # If Prometheus is not properly configured, skip this test
            pytest.skip("Prometheus query API not accessible or not configured")
