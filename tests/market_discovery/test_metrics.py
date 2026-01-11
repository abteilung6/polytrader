"""Tests for market discovery metrics collection."""

from unittest.mock import MagicMock, patch

import pytest

from polytrader.market_discovery import MarketDiscoveryService, MarketState
from polytrader.market_discovery.metrics import (
    record_cache_hit,
    record_cache_miss,
    record_discovery_attempt,
    record_discovery_failure,
    record_discovery_latency,
    record_windows_searched,
    update_cache_size_gauge,
    update_windows_checked_gauge,
)
from polytrader.obs.metrics import MemoryMetricsCollector, set_metrics_collector


@pytest.fixture
def metrics_collector() -> MemoryMetricsCollector:
    """Create a fresh metrics collector for each test."""
    collector = MemoryMetricsCollector()
    set_metrics_collector(collector)
    return collector


@pytest.mark.asyncio
async def test_record_discovery_attempt_success(metrics_collector: MemoryMetricsCollector) -> None:
    """Test recording successful discovery attempt."""
    pattern = "btc-updown-15m"

    record_discovery_attempt(pattern, success=True)

    count = metrics_collector.get_counter(
        "market_discovery_attempts_total", labels={"pattern": pattern, "success": "true"}
    )
    assert count == 1


@pytest.mark.asyncio
async def test_record_discovery_attempt_failure(metrics_collector: MemoryMetricsCollector) -> None:
    """Test recording failed discovery attempt."""
    pattern = "btc-updown-15m"

    record_discovery_attempt(pattern, success=False)

    count = metrics_collector.get_counter(
        "market_discovery_attempts_total", labels={"pattern": pattern, "success": "false"}
    )
    assert count == 1


@pytest.mark.asyncio
async def test_record_discovery_failure(metrics_collector: MemoryMetricsCollector) -> None:
    """Test recording discovery failure with reason and error_class."""
    pattern = "btc-updown-15m"
    reason = "no_market_found"
    error_class = "retryable"

    record_discovery_failure(pattern, reason, error_class)

    count = metrics_collector.get_counter(
        "market_discovery_failures_total",
        labels={"pattern": pattern, "reason": reason, "error_class": error_class},
    )
    assert count == 1


@pytest.mark.asyncio
async def test_record_discovery_latency(metrics_collector: MemoryMetricsCollector) -> None:
    """Test recording discovery latency histogram."""
    pattern = "btc-updown-15m"
    latency_ms = 123.45
    success = True

    record_discovery_latency(pattern, latency_ms, success)

    percentiles = metrics_collector.get_histogram_percentiles(
        "market_discovery_latency_ms",
        labels={"pattern": pattern, "success": "true"},
    )
    assert len(percentiles) > 0
    assert percentiles[0.5] == latency_ms  # Single value, median is the value


@pytest.mark.asyncio
async def test_record_windows_searched(metrics_collector: MemoryMetricsCollector) -> None:
    """Test recording windows searched histogram."""
    pattern = "btc-updown-15m"
    windows_checked = 5

    record_windows_searched(pattern, windows_checked)

    percentiles = metrics_collector.get_histogram_percentiles(
        "market_discovery_windows_searched",
        labels={"pattern": pattern},
    )
    assert len(percentiles) > 0
    assert percentiles[0.5] == float(windows_checked)


@pytest.mark.asyncio
async def test_record_cache_hit(metrics_collector: MemoryMetricsCollector) -> None:
    """Test recording cache hit."""
    pattern = "btc-updown-15m"

    record_cache_hit(pattern)

    count = metrics_collector.get_counter(
        "market_discovery_cache_hits_total", labels={"pattern": pattern}
    )
    assert count == 1


@pytest.mark.asyncio
async def test_record_cache_miss(metrics_collector: MemoryMetricsCollector) -> None:
    """Test recording cache miss."""
    pattern = "btc-updown-15m"

    record_cache_miss(pattern)

    count = metrics_collector.get_counter(
        "market_discovery_cache_misses_total", labels={"pattern": pattern}
    )
    assert count == 1


@pytest.mark.asyncio
async def test_update_windows_checked_gauge(metrics_collector: MemoryMetricsCollector) -> None:
    """Test updating windows checked gauge."""
    pattern = "btc-updown-15m"
    windows_checked = 10

    update_windows_checked_gauge(pattern, windows_checked)

    value = metrics_collector.get_gauge(
        "market_discovery_windows_checked", labels={"pattern": pattern}
    )
    assert value == float(windows_checked)


@pytest.mark.asyncio
async def test_update_cache_size_gauge(metrics_collector: MemoryMetricsCollector) -> None:
    """Test updating cache size gauge."""
    cache_size = 5

    update_cache_size_gauge(cache_size)

    value = metrics_collector.get_gauge("market_discovery_cache_size")
    assert value == float(cache_size)


@pytest.mark.asyncio
async def test_service_records_metrics_on_success(
    metrics_collector: MemoryMetricsCollector,
) -> None:
    """Test that MarketDiscoveryService records metrics on successful discovery."""
    from unittest.mock import AsyncMock

    from polytrader.adapters.polymarket.market_data import GammaClient

    pattern = "btc-updown-15m"
    gamma_client = MagicMock(spec=GammaClient)
    market = MagicMock()
    gamma_client.get_market_by_slug = MagicMock(return_value=market)

    discovery = MarketDiscoveryService(gamma_client=gamma_client)

    with patch.object(discovery, "get_market_state", new_callable=AsyncMock) as mock_state:
        mock_state.return_value = MarketState.ACTIVE

        result = await discovery.get_current_market(pattern)

        assert result is not None

        # Verify metrics were recorded
        success_count = metrics_collector.get_counter(
            "market_discovery_attempts_total", labels={"pattern": pattern, "success": "true"}
        )
        assert success_count == 1

        # Check latency histogram (labels are converted to tuple keys)
        latency_key = tuple(sorted([("pattern", pattern), ("success", "true")]))
        latency_values = metrics_collector._histograms.get("market_discovery_latency_ms", {}).get(
            latency_key, []
        )
        assert len(latency_values) == 1


@pytest.mark.asyncio
async def test_service_records_metrics_on_failure(
    metrics_collector: MemoryMetricsCollector,
) -> None:
    """Test that MarketDiscoveryService records metrics on failed discovery."""
    from unittest.mock import AsyncMock

    from polytrader.adapters.polymarket.market_data import GammaClient

    pattern = "btc-updown-15m"
    gamma_client = MagicMock(spec=GammaClient)
    gamma_client.get_market_by_slug = MagicMock(return_value=None)

    discovery = MarketDiscoveryService(gamma_client=gamma_client, max_windows_ahead=2)

    with patch.object(discovery, "get_market_state", new_callable=AsyncMock) as mock_state:
        mock_state.return_value = MarketState.NOT_FOUND

        result = await discovery.get_current_market(pattern)

        assert result is None

        # Verify metrics were recorded
        failure_count = metrics_collector.get_counter(
            "market_discovery_attempts_total", labels={"pattern": pattern, "success": "false"}
        )
        assert failure_count == 1

        failure_reason_count = metrics_collector.get_counter(
            "market_discovery_failures_total",
            labels={"pattern": pattern, "reason": "no_market_found", "error_class": "retryable"},
        )
        assert failure_reason_count == 1


@pytest.mark.asyncio
async def test_service_records_cache_metrics(
    metrics_collector: MemoryMetricsCollector,
) -> None:
    """Test that MarketDiscoveryService records cache hit/miss metrics."""
    from unittest.mock import AsyncMock

    from polytrader.adapters.polymarket.market_data import GammaClient

    pattern = "btc-updown-15m"
    gamma_client = MagicMock(spec=GammaClient)
    market = MagicMock()
    gamma_client.get_market_by_slug = MagicMock(return_value=market)

    discovery = MarketDiscoveryService(gamma_client=gamma_client)

    with patch.object(discovery, "get_market_state", new_callable=AsyncMock) as mock_state:
        mock_state.return_value = MarketState.ACTIVE

        # First call - should be cache miss
        result1 = await discovery.get_current_market(pattern)
        assert result1 is not None

        miss_count = metrics_collector.get_counter(
            "market_discovery_cache_misses_total", labels={"pattern": pattern}
        )
        assert miss_count == 1

        # Second call - should be cache hit
        result2 = await discovery.get_current_market(pattern)
        assert result2 is not None

        hit_count = metrics_collector.get_counter(
            "market_discovery_cache_hits_total", labels={"pattern": pattern}
        )
        assert hit_count == 1
