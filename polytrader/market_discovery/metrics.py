"""Market discovery metrics collection per observability.mdc §4.

This module provides functions for recording market discovery metrics:
- Discovery attempts and success/failure rates
- Cache hit/miss rates
- Latency metrics (discovery latency, windows searched)
- Search depth metrics
"""

from polytrader.obs.metrics import get_metrics_collector


def record_discovery_attempt(pattern: str, success: bool) -> None:
    """Record a market discovery attempt.

    Per observability.mdc §4: Track market_discovery_attempts_total.

    Args:
        pattern: Market pattern being searched (e.g., "btc-updown-15m")
        success: Whether discovery was successful
    """
    metrics = get_metrics_collector()
    metrics.increment_counter(
        "market_discovery_attempts_total",
        labels={
            "pattern": pattern,
            "success": str(success).lower(),
        },
    )


def record_discovery_failure(pattern: str, reason: str, error_class: str = "unknown") -> None:
    """Record a market discovery failure.

    Per observability.mdc §4: Track market_discovery_failures_total with reason and error_class.

    Args:
        pattern: Market pattern being searched
        reason: Failure reason (e.g., "no_market_found", "api_error", "invalid_pattern")
        error_class: Error classification ("retryable" or "fatal")
    """
    metrics = get_metrics_collector()
    metrics.increment_counter(
        "market_discovery_failures_total",
        labels={
            "pattern": pattern,
            "reason": reason,
            "error_class": error_class,
        },
    )


def record_discovery_latency(pattern: str, latency_ms: float, success: bool) -> None:
    """Record market discovery latency.

    Per observability.mdc §4: Track market_discovery_latency_ms histogram.

    Args:
        pattern: Market pattern being searched
        latency_ms: Discovery latency in milliseconds
        success: Whether discovery was successful
    """
    metrics = get_metrics_collector()
    metrics.record_histogram(
        "market_discovery_latency_ms",
        latency_ms,
        labels={
            "pattern": pattern,
            "success": str(success).lower(),
        },
    )


def record_windows_searched(pattern: str, windows_checked: int) -> None:
    """Record number of windows searched during discovery.

    Tracks distribution of search depth.

    Args:
        pattern: Market pattern being searched
        windows_checked: Number of windows checked
    """
    metrics = get_metrics_collector()
    metrics.record_histogram(
        "market_discovery_windows_searched",
        float(windows_checked),
        labels={"pattern": pattern},
    )


def record_cache_hit(pattern: str) -> None:
    """Record a cache hit.

    Per observability.mdc §4: Track market_discovery_cache_hits_total.

    Args:
        pattern: Market pattern that was cached
    """
    metrics = get_metrics_collector()
    metrics.increment_counter(
        "market_discovery_cache_hits_total",
        labels={"pattern": pattern},
    )


def record_cache_miss(pattern: str) -> None:
    """Record a cache miss.

    Per observability.mdc §4: Track market_discovery_cache_misses_total.

    Args:
        pattern: Market pattern that was not cached
    """
    metrics = get_metrics_collector()
    metrics.increment_counter(
        "market_discovery_cache_misses_total",
        labels={"pattern": pattern},
    )


def update_windows_checked_gauge(pattern: str, windows_checked: int) -> None:
    """Update gauge for current search depth.

    Per observability.mdc §4: Track market_discovery_windows_checked gauge.

    Args:
        pattern: Market pattern being searched
        windows_checked: Current number of windows checked
    """
    metrics = get_metrics_collector()
    metrics.set_gauge(
        "market_discovery_windows_checked",
        float(windows_checked),
        labels={"pattern": pattern},
    )


def update_cache_size_gauge(cache_size: int) -> None:
    """Update gauge for cache size.

    Per observability.mdc §4: Track market_discovery_cache_size gauge.

    Args:
        cache_size: Number of cached patterns
    """
    metrics = get_metrics_collector()
    metrics.set_gauge("market_discovery_cache_size", float(cache_size))
