"""Integration tests for SystemSupervisor with EventSink.

Tests that EventSink is properly integrated into SystemSupervisor:
- EventSink is initialized during startup
- EventSink runs as a separate task
- Events are persisted to PostgreSQL
- EventSink handles failures gracefully
- EventSink is stopped cleanly on shutdown
"""

import asyncio
from collections.abc import AsyncGenerator

import pytest

from polytrader.events import EventBus
from polytrader.events.types import SystemStartedEvent
from polytrader.oms import OMSCore
from polytrader.oms.idempotency import IdempotencyStore
from polytrader.oms.store import InMemoryOrderStore
from polytrader.portfolio import PortfolioService
from polytrader.risk import RiskChecker, get_default_limits
from polytrader.risk.engine import RiskEngine
from polytrader.store import MemoryMarketDataStore
from polytrader.supervisor.system import SystemSupervisor


@pytest.fixture
async def supervisor_with_sink(
    postgres_test_url: str, postgres_db: None, monkeypatch: pytest.MonkeyPatch
) -> AsyncGenerator[SystemSupervisor, None]:
    """Create SystemSupervisor with EventSink for testing."""
    from urllib.parse import urlparse

    # Migrations are run by postgres_db fixture

    # Parse database URL and set environment variables for get_database_url()
    parsed = urlparse(postgres_test_url)
    monkeypatch.setenv("DB_HOST", parsed.hostname or "localhost")
    monkeypatch.setenv("DB_PORT", str(parsed.port or 5432))
    monkeypatch.setenv("DB_DATABASE", parsed.path.lstrip("/") if parsed.path else "polytrader_test")
    monkeypatch.setenv("DB_USER", parsed.username or "test_user")
    monkeypatch.setenv("DB_PASSWORD", parsed.password or "test_password")

    # Create event bus (no store - EventSink will handle persistence)
    bus = EventBus()

    # Create market data store
    store = MemoryMarketDataStore()

    # Create service factories
    # Use shared OMS store (required for OMS core)
    oms_store = InMemoryOrderStore(bus)

    def portfolio_factory() -> PortfolioService:
        return PortfolioService(bus=bus, store=store)

    def risk_factory() -> RiskChecker:
        risk_limits = get_default_limits()
        risk_engine = RiskEngine(limits=risk_limits)
        return RiskChecker(bus=bus, engine=risk_engine, store=store)

    def oms_factory() -> OMSCore:
        idempotency_store = IdempotencyStore()
        return OMSCore(bus=bus, store=oms_store, idempotency_store=idempotency_store)

    # Create supervisor
    supervisor = SystemSupervisor(
        bus=bus,
        store=store,
        portfolio_service_factory=portfolio_factory,
        risk_checker_factory=risk_factory,
        oms_core_factory=oms_factory,
    )

    # Start supervisor
    await supervisor.start()

    yield supervisor

    # Stop supervisor
    await supervisor.stop()


@pytest.mark.asyncio
async def test_supervisor_initializes_event_sink(
    supervisor_with_sink: SystemSupervisor,
) -> None:
    """Test that SystemSupervisor initializes EventSink during startup."""
    assert supervisor_with_sink._event_sink is not None
    assert supervisor_with_sink._event_sink_task is not None
    assert not supervisor_with_sink._event_sink_task.done()


@pytest.mark.asyncio
async def test_supervisor_persists_events_to_database(
    supervisor_with_sink: SystemSupervisor,
    postgres_test_url: str,
) -> None:
    """Test that events published during supervisor operation are persisted."""
    from polytrader.events import SYSTEM_LIFECYCLE

    # Publish an event
    event = SystemStartedEvent()
    await supervisor_with_sink.bus.publish(SYSTEM_LIFECYCLE, event)

    # Wait for EventSink to flush (flush_interval is 1.0s by default)
    await asyncio.sleep(1.5)

    # Verify event was persisted
    if supervisor_with_sink._event_sink is not None:
        store = supervisor_with_sink._event_sink._store
        events = list(store.read_stream())
        assert len(events) >= 1
        assert any(e.event_id == event.event_id for e in events)


@pytest.mark.asyncio
async def test_supervisor_stops_event_sink_cleanly(
    supervisor_with_sink: SystemSupervisor,
) -> None:
    """Test that EventSink is stopped cleanly when supervisor stops."""
    # Verify EventSink is running
    assert supervisor_with_sink._event_sink is not None
    assert supervisor_with_sink._event_sink_task is not None
    assert not supervisor_with_sink._event_sink_task.done()

    # Stop supervisor
    await supervisor_with_sink.stop()

    # Verify EventSink is stopped
    assert supervisor_with_sink._event_sink is None
    assert supervisor_with_sink._event_sink_task is None


@pytest.mark.asyncio
async def test_supervisor_handles_event_sink_failure_gracefully(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that supervisor handles EventSink initialization failure gracefully."""

    # Mock get_database_url to raise an exception (simulating missing/invalid config)
    # This is more reliable than deleting env vars, as DatabaseConfig can load from .env file
    def failing_get_database_url(*args: object, **kwargs: object) -> str:
        raise ValueError("Database configuration missing: required fields not set")

    monkeypatch.setattr("polytrader.supervisor.system.get_database_url", failing_get_database_url)

    # Create event bus
    bus = EventBus()

    # Create market data store
    store = MemoryMarketDataStore()

    # Create service factories
    # Use shared OMS store (required for OMS core)
    oms_store = InMemoryOrderStore(bus)

    def portfolio_factory() -> PortfolioService:
        return PortfolioService(bus=bus, store=store)

    def risk_factory() -> RiskChecker:
        risk_limits = get_default_limits()
        risk_engine = RiskEngine(limits=risk_limits)
        return RiskChecker(bus=bus, engine=risk_engine, store=store)

    def oms_factory() -> OMSCore:
        idempotency_store = IdempotencyStore()
        return OMSCore(bus=bus, store=oms_store, idempotency_store=idempotency_store)

    # Create supervisor
    supervisor = SystemSupervisor(
        bus=bus,
        store=store,
        portfolio_service_factory=portfolio_factory,
        risk_checker_factory=risk_factory,
        oms_core_factory=oms_factory,
    )

    # Start supervisor (should handle EventSink failure gracefully)
    await supervisor.start()

    # Verify supervisor started even though EventSink failed
    assert supervisor._running is True
    assert supervisor._event_sink is None  # EventSink not initialized due to error

    # Stop supervisor
    await supervisor.stop()


@pytest.mark.asyncio
async def test_supervisor_event_sink_task_runs_independently(
    supervisor_with_sink: SystemSupervisor,
) -> None:
    """Test that EventSink task runs independently of other services."""
    # Verify EventSink task is running
    assert supervisor_with_sink._event_sink_task is not None
    assert not supervisor_with_sink._event_sink_task.done()

    # Verify other service tasks are also running
    assert supervisor_with_sink._risk_checker_task is not None
    assert supervisor_with_sink._oms_core_task is not None

    # All tasks should be running concurrently
    await asyncio.sleep(0.1)
    assert not supervisor_with_sink._event_sink_task.done()
    assert not supervisor_with_sink._risk_checker_task.done()
    assert not supervisor_with_sink._oms_core_task.done()
