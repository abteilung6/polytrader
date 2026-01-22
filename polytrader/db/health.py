"""Health checks for tick storage.

Per flows.mdc §2: Health gates must validate all critical components.
This module provides health check functions for tick storage connectivity and functionality.

Per architecture: Health checks are non-blocking, fast (< 2s), and return structured results.
"""

import time
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import uuid4

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from polytrader.db.repository import MarketTickRepository


class TickStorageHealth(BaseModel):
    """Tick storage health status.

    Per flows.mdc §2: Health checks return structured status.
    This model captures the current state of tick storage health checks.

    Attributes:
        connected: Whether database connection is healthy
        write_healthy: Whether write test passed
        read_healthy: Whether read test passed
        write_latency_ms: Write test latency in milliseconds (None if test failed)
        read_latency_ms: Read test latency in milliseconds (None if test failed)
        error_message: Error details if unhealthy (None if healthy)
    """

    connected: bool = Field(description="Whether database connection is healthy")
    write_healthy: bool = Field(description="Whether write test passed")
    read_healthy: bool = Field(description="Whether read test passed")
    write_latency_ms: float | None = Field(
        default=None, description="Write test latency in milliseconds"
    )
    read_latency_ms: float | None = Field(
        default=None, description="Read test latency in milliseconds"
    )
    error_message: str | None = Field(default=None, description="Error details if unhealthy")


async def check_tick_storage_connectivity(
    repository: "MarketTickRepository",
) -> bool:
    """Check tick storage database connectivity.

    Per flows.mdc §2: Health checks validate connectivity.

    Args:
        repository: MarketTickRepository instance

    Returns:
        True if connection is healthy, False otherwise

    Note:
        This is a lightweight check (doesn't write/read data).
        Uses a simple query to verify connection.
    """
    try:
        # Try to query database (simple check)
        # Use get_markets() as it's lightweight and doesn't require data
        # This will raise an exception if session is closed or connection is invalid
        await repository.get_markets()
        return True
    except Exception:
        return False


async def check_tick_storage_write(
    repository: "MarketTickRepository",
) -> tuple[bool, float]:
    """Check tick storage write functionality.

    Per flows.mdc §2: Health checks validate write capability.

    Args:
        repository: MarketTickRepository instance

    Returns:
        Tuple of (success: bool, latency_ms: float)
        If success is False, latency_ms is 0.0

    Note:
        Creates a test tick and immediately deletes it (cleanup).
        Uses a unique tick_id to avoid conflicts.
    """
    from sqlalchemy import delete

    from polytrader.db.models import MarketTickRecord

    # Generate unique test tick ID
    test_tick_id = uuid4()
    test_ts_wall = datetime.now(UTC)

    start_time = time.perf_counter()

    try:
        # Create test tick
        await repository.create_tick(
            tick_id=test_tick_id,
            ts_wall=test_ts_wall,
            ts_mono=time.monotonic(),
            market_slug="__health_check__",
            outcome="UP",
            best_bid=Decimal("0.50"),
            best_ask=Decimal("0.50"),
            mid=Decimal("0.50"),
            spread=Decimal("0.00"),
            spread_bps=Decimal("0.00"),
            event_id=None,
            run_id="__health_check__",
        )

        latency_ms = (time.perf_counter() - start_time) * 1000.0

        # Cleanup: delete test tick
        try:
            stmt = delete(MarketTickRecord).where(
                MarketTickRecord.tick_id == test_tick_id,
                MarketTickRecord.ts_wall == test_ts_wall,
            )
            await repository.session.execute(stmt)
            await repository.session.commit()
        except Exception:
            # If cleanup fails, rollback but don't fail health check
            await repository.session.rollback()

        return True, latency_ms
    except Exception:
        latency_ms = (time.perf_counter() - start_time) * 1000.0
        return False, latency_ms


async def check_tick_storage_read(
    repository: "MarketTickRepository",
) -> tuple[bool, float]:
    """Check tick storage read functionality.

    Per flows.mdc §2: Health checks validate read capability.

    Args:
        repository: MarketTickRepository instance

    Returns:
        Tuple of (success: bool, latency_ms: float)
        If success is False, latency_ms is 0.0

    Note:
        Uses get_markets() as a lightweight read test.
        Doesn't require existing data (works on empty database).
    """
    start_time = time.perf_counter()

    try:
        # Simple read test (get_markets is lightweight)
        await repository.get_markets()
        latency_ms = (time.perf_counter() - start_time) * 1000.0
        return True, latency_ms
    except Exception:
        latency_ms = (time.perf_counter() - start_time) * 1000.0
        return False, latency_ms


async def check_tick_storage_health(
    repository: "MarketTickRepository",
    write_latency_threshold_ms: float = 100.0,
    read_latency_threshold_ms: float = 50.0,
) -> TickStorageHealth:
    """Comprehensive tick storage health check.

    Per flows.mdc §2: Health checks validate all critical functionality.

    Args:
        repository: MarketTickRepository instance
        write_latency_threshold_ms: Maximum write latency for health (default: 100ms)
        read_latency_threshold_ms: Maximum read latency for health (default: 50ms)

    Returns:
        TickStorageHealth with all health check results

    Note:
        Health checks are fast (< 2s total) and non-blocking.
        Failures are captured but don't raise exceptions.
    """
    error_messages: list[str] = []

    # 1. Check connectivity
    connected = await check_tick_storage_connectivity(repository)
    if not connected:
        error_messages.append("Database connection failed")

    # 2. Check write (only if connected)
    write_healthy = False
    write_latency_ms: float | None = None
    if connected:
        write_success, write_latency = await check_tick_storage_write(repository)
        write_healthy = write_success and write_latency <= write_latency_threshold_ms
        write_latency_ms = write_latency if write_success else None
        if not write_success:
            error_messages.append(f"Write test failed (latency: {write_latency:.2f}ms)")
        elif write_latency > write_latency_threshold_ms:
            error_messages.append(
                f"Write latency too high: {write_latency:.2f}ms > {write_latency_threshold_ms}ms"
            )
    else:
        error_messages.append("Write test skipped (not connected)")

    # 3. Check read (only if connected)
    read_healthy = False
    read_latency_ms: float | None = None
    if connected:
        read_success, read_latency = await check_tick_storage_read(repository)
        read_healthy = read_success and read_latency <= read_latency_threshold_ms
        read_latency_ms = read_latency if read_success else None
        if not read_success:
            error_messages.append(f"Read test failed (latency: {read_latency:.2f}ms)")
        elif read_latency > read_latency_threshold_ms:
            error_messages.append(
                f"Read latency too high: {read_latency:.2f}ms > {read_latency_threshold_ms}ms"
            )
    else:
        error_messages.append("Read test skipped (not connected)")

    return TickStorageHealth(
        connected=connected,
        write_healthy=write_healthy,
        read_healthy=read_healthy,
        write_latency_ms=write_latency_ms,
        read_latency_ms=read_latency_ms,
        error_message="; ".join(error_messages) if error_messages else None,
    )
