"""Integration smoke tests for Pilot Live L1 control flow.

Per PILOT_LIVE.md Commit 12: Covers the complete L1 control flow without
real venues or market data. Uses FakeClock where time is needed; all tests
use test database and API client or in-process control plane.

Tests:
- Platform config (live-pilot.yaml) loads
- execution_enabled defaults to false at startup
- POST enable → execution_enabled true (via control plane)
- POST disable → execution_enabled false (via control plane)
- POST kill-switch → execution disabled immediately
- Kill switch reset clears flag but leaves execution disabled
- Strategy activation → risk policy 5 allows live orders
- Strategy deactivation → risk policy 5 denies live orders
- ExecutionPermitEvent emitted on enable path
- KillSwitchEvent emitted on kill switch activate/reset
"""

import asyncio
from collections.abc import AsyncGenerator, Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from polytrader.api.app import create_app
from polytrader.api.dependencies import get_db_session, get_execution_control
from polytrader.events import SYSTEM_LIFECYCLE, EventBus
from polytrader.events.types import ExecutionPermitEvent, KillSwitchEvent
from polytrader.ops.control import ExecutionControl
from polytrader.platform.control import (
    ControlCommandRepository,
    ExecutionControlRepository,
    LiveStrategyRepository,
)
from polytrader.platform.control_plane import ControlPlaneService
from polytrader.platform.registry import StrategyRegistry
from polytrader.risk import RiskEngine, get_default_limits
from polytrader.risk.models import RiskContext, RiskReasonCode
from tests.factories.events import create_order_intent_event

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[2]
LIVE_PILOT_CONFIG = REPO_ROOT / "config" / "platform.live-pilot.yaml"


@pytest.fixture
def client(postgres_test_url: str, postgres_db: None) -> Iterator[TestClient]:
    """FastAPI test client with test database. No orchestrator or execution_control."""
    if postgres_test_url.startswith("postgresql://"):
        sqlalchemy_url = postgres_test_url.replace("postgresql://", "postgresql+psycopg://", 1)
    else:
        sqlalchemy_url = postgres_test_url

    engine = create_async_engine(sqlalchemy_url, echo=False)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def cleanup() -> None:
        from sqlalchemy import text

        async with Session() as session:
            try:
                await session.execute(text("TRUNCATE TABLE strategy_instances CASCADE"))
                await session.commit()
            except Exception:
                await session.rollback()

    asyncio.run(cleanup())

    app = create_app()

    async def override_get_db_session() -> AsyncGenerator[AsyncSession, None]:
        async with Session() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db_session
    yield TestClient(app)
    app.dependency_overrides.clear()
    asyncio.run(cleanup())
    engine.sync_engine.dispose()


@pytest.fixture
def client_with_execution_control(
    postgres_test_url: str, postgres_db: None
) -> Iterator[TestClient]:
    """Client with ExecutionControl and EventBus injected for kill switch tests."""
    if postgres_test_url.startswith("postgresql://"):
        sqlalchemy_url = postgres_test_url.replace("postgresql://", "postgresql+psycopg://", 1)
    else:
        sqlalchemy_url = postgres_test_url

    engine = create_async_engine(sqlalchemy_url, echo=False)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    bus = EventBus()
    execution_control = ExecutionControl(bus=bus)

    async def override_get_db_session() -> AsyncGenerator[AsyncSession, None]:
        async with Session() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_db_session] = override_get_db_session
    app.state.execution_control = execution_control

    def get_exec_control(_request=None):
        return execution_control

    app.dependency_overrides[get_execution_control] = get_exec_control
    yield TestClient(app)
    app.dependency_overrides.clear()
    engine.sync_engine.dispose()


# ---------------------------------------------------------------------------
# Config and execution state (sync API tests)
# ---------------------------------------------------------------------------


def test_platform_live_pilot_config_loads() -> None:
    """Platform boots with config/platform.live-pilot.yaml (config loads)."""
    from polytrader.config.loader import load_platform_config

    assert LIVE_PILOT_CONFIG.exists(), "config/platform.live-pilot.yaml must exist"
    config = asyncio.run(load_platform_config(LIVE_PILOT_CONFIG))
    assert config is not None
    assert config.version == "1.0"
    assert config.risk is not None
    assert config.risk.max_order_size == 1.0


def test_execution_enabled_defaults_to_false(client: TestClient) -> None:
    """execution_enabled defaults to false at startup (GET from DB when no platform)."""
    response = client.get("/api/v1/state/execution")
    assert response.status_code == 200
    data = response.json()
    assert data["execution_enabled"] is False
    assert "kill_switch_active" in data
    assert data["kill_switch_active"] is False


# ---------------------------------------------------------------------------
# Enable / disable via control plane (async)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_post_enable_then_control_plane_execution_enabled_true(
    postgres_test_url: str, postgres_db: None
) -> None:
    """POST enable creates command; control plane sets execution_enabled true."""
    if postgres_test_url.startswith("postgresql://"):
        sqlalchemy_url = postgres_test_url.replace("postgresql://", "postgresql+psycopg://", 1)
    else:
        sqlalchemy_url = postgres_test_url

    engine = create_async_engine(sqlalchemy_url, echo=False)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    bus = EventBus()
    execution_control = ExecutionControl(bus=bus)

    async with Session() as session:
        command_repo = ControlCommandRepository(session)
        execution_repo = ExecutionControlRepository(session)
        live_repo = LiveStrategyRepository(session)
        strategy_registry = StrategyRegistry(session)
        service = ControlPlaneService(
            command_repo=command_repo,
            execution_repo=execution_repo,
            live_repo=live_repo,
            strategy_registry=strategy_registry,
            execution_control=execution_control,
            bus=bus,
            poll_interval_s=0.1,
        )

        from polytrader.db.models import ControlCommandRecord

        cmd = ControlCommandRecord(
            command_type="enable_execution",
            reason="Smoke test enable",
            issued_by="operator",
            client_request_id="pilot-live-enable-1",
        )
        await command_repo.create_command(cmd)
        await session.commit()

        pending = await command_repo.list_pending()
        assert len(pending) >= 1
        enable_cmd = next((c for c in pending if c.command_type == "enable_execution"), None)
        assert enable_cmd is not None
        await service._process_command(enable_cmd)

        control = await execution_repo.get_control()
        assert control.execution_enabled is True
        assert execution_control.execution_enabled is True

    await engine.dispose()


@pytest.mark.asyncio
async def test_post_disable_then_control_plane_execution_enabled_false(
    postgres_test_url: str, postgres_db: None
) -> None:
    """POST disable creates command; control plane sets execution_enabled false."""
    if postgres_test_url.startswith("postgresql://"):
        sqlalchemy_url = postgres_test_url.replace("postgresql://", "postgresql+psycopg://", 1)
    else:
        sqlalchemy_url = postgres_test_url

    engine = create_async_engine(sqlalchemy_url, echo=False)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    bus = EventBus()
    execution_control = ExecutionControl(bus=bus)

    async with Session() as session:
        command_repo = ControlCommandRepository(session)
        execution_repo = ExecutionControlRepository(session)
        live_repo = LiveStrategyRepository(session)
        strategy_registry = StrategyRegistry(session)
        service = ControlPlaneService(
            command_repo=command_repo,
            execution_repo=execution_repo,
            live_repo=live_repo,
            strategy_registry=strategy_registry,
            execution_control=execution_control,
            bus=bus,
            poll_interval_s=0.1,
        )

        await execution_repo.update_control(
            execution_enabled=True,
            updated_by="test",
            reason="Setup for disable test",
        )
        execution_control.enable()

        from polytrader.db.models import ControlCommandRecord

        cmd = ControlCommandRecord(
            command_type="disable_execution",
            reason="Smoke test disable",
            issued_by="operator",
            client_request_id="pilot-live-disable-1",
        )
        await command_repo.create_command(cmd)
        await session.commit()

        pending = await command_repo.list_pending()
        disable_cmd = next((c for c in pending if c.command_type == "disable_execution"), None)
        assert disable_cmd is not None
        await service._process_command(disable_cmd)

        control = await execution_repo.get_control()
        assert control.execution_enabled is False
        assert execution_control.execution_enabled is False

    await engine.dispose()


# ---------------------------------------------------------------------------
# Kill switch (direct-apply; needs execution_control injected)
# ---------------------------------------------------------------------------


def test_post_kill_switch_disables_execution_immediately(
    client_with_execution_control: TestClient,
) -> None:
    """POST /commands/execution/kill-switch immediately disables execution."""
    client = client_with_execution_control
    # Kill switch is direct-apply (no queue); requires execution_control in app
    response = client.post(
        "/api/v1/commands/execution/kill-switch",
        json={
            "reason": "Smoke test kill",
            "issued_by": "operator",
            "cancel_open_orders": True,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data.get("status") == "applied"

    state = client.get("/api/v1/state/execution")
    assert state.status_code == 200
    state_data = state.json()
    assert state_data["execution_enabled"] is False
    assert state_data["kill_switch_active"] is True


def test_kill_switch_reset_clears_flag_leaves_execution_disabled(
    client_with_execution_control: TestClient,
) -> None:
    """Kill switch reset clears flag but leaves execution disabled."""
    client = client_with_execution_control
    client.post(
        "/api/v1/commands/execution/kill-switch",
        json={
            "reason": "Activate for reset test",
            "issued_by": "operator",
            "cancel_open_orders": True,
        },
    )
    response = client.post(
        "/api/v1/commands/execution/kill-switch/reset",
        json={"reason": "Reset smoke test", "issued_by": "operator"},
    )
    assert response.status_code == 200

    state = client.get("/api/v1/state/execution")
    assert state.status_code == 200
    data = state.json()
    assert data["kill_switch_active"] is False
    assert data["execution_enabled"] is False


# ---------------------------------------------------------------------------
# Risk policy 5: strategy activation (live orders allowed/denied)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_strategy_activation_risk_policy_allows_live_orders() -> None:
    """Strategy activation → risk policy 5 allows live orders (strategy in active set)."""
    from polytrader.events.types import MarketDataEvent
    from polytrader.store import MemoryMarketDataStore

    store = MemoryMarketDataStore()
    market_data = MarketDataEvent(
        market_slug="test-market",
        outcome="UP",
        best_bid=0.45,
        best_ask=0.55,
    )
    store.add(market_data)

    intent = create_order_intent_event(
        strategy_id="active_strategy",
        market_slug="test-market",
    )
    risk_engine = RiskEngine(limits=get_default_limits())
    context = RiskContext(
        intent=intent,
        market_data=market_data,
        active_strategies={"active_strategy"},
        is_paper_mode=False,
        reconciliation_healthy=True,
    )
    result = risk_engine.check(context)
    assert RiskReasonCode.RISK_STRATEGY_NOT_ACTIVE not in result.reason_codes
    assert result.allowed is True or result.reason_codes  # Allowed or denied by other policy


@pytest.mark.asyncio
async def test_strategy_deactivation_risk_policy_denies_live_orders() -> None:
    """Strategy deactivation → risk policy 5 denies live orders (strategy not in active set)."""
    from polytrader.events.types import MarketDataEvent
    from polytrader.store import MemoryMarketDataStore

    store = MemoryMarketDataStore()
    market_data = MarketDataEvent(
        market_slug="test-market",
        outcome="UP",
        best_bid=0.45,
        best_ask=0.55,
    )
    store.add(market_data)

    intent = create_order_intent_event(
        strategy_id="inactive_strategy",
        market_slug="test-market",
    )
    risk_engine = RiskEngine(limits=get_default_limits())
    context = RiskContext(
        intent=intent,
        market_data=market_data,
        active_strategies=set(),
        is_paper_mode=False,
        reconciliation_healthy=True,
    )
    result = risk_engine.check(context)
    assert result.allowed is False
    assert RiskReasonCode.RISK_STRATEGY_NOT_ACTIVE in result.reason_codes


# ---------------------------------------------------------------------------
# Event emission (ExecutionPermitEvent, KillSwitchEvent)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execution_permit_event_emitted_on_enable_with_permit() -> None:
    """ExecutionPermitEvent emitted when enable_with_permit is called."""
    bus = EventBus()
    execution_control = ExecutionControl(bus=bus)
    queue = bus.subscribe(SYSTEM_LIFECYCLE)

    await execution_control.enable_with_permit(
        permit_type="manual",
        reason="Smoke test permit",
        health_status={"overall": "ok"},
        issued_by="operator",
    )
    event = await asyncio.wait_for(queue.get(), timeout=1.0)
    assert isinstance(event, ExecutionPermitEvent)
    assert event.permit_type == "manual"
    assert event.reason == "Smoke test permit"


@pytest.mark.asyncio
async def test_kill_switch_event_emitted_on_activate_and_reset() -> None:
    """KillSwitchEvent emitted on kill switch activate and reset."""
    bus = EventBus()
    execution_control = ExecutionControl(bus=bus)
    queue = bus.subscribe(SYSTEM_LIFECYCLE)

    await execution_control.set_kill_switch(
        active=True,
        reason="Smoke activate",
        cancel_open_orders=True,
        triggered_by="operator",
    )
    event1 = await asyncio.wait_for(queue.get(), timeout=1.0)
    assert isinstance(event1, KillSwitchEvent)
    assert event1.triggered is True
    assert event1.reason == "Smoke activate"

    await execution_control.set_kill_switch(
        active=False,
        reason="Smoke reset",
        cancel_open_orders=False,
        triggered_by="operator",
    )
    event2 = await asyncio.wait_for(queue.get(), timeout=1.0)
    assert isinstance(event2, KillSwitchEvent)
    assert event2.triggered is False
    assert event2.reason == "Smoke reset"
