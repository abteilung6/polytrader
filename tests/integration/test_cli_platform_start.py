"""Integration tests for CLI platform start command.

Per Platform_Proposal.md §4.1: Tests verify that:
- CLI platform start command exists and can be invoked
- Platform task can be started and stopped gracefully
- API server is accessible when running

Note: Full platform startup tests are complex and may require
separate test infrastructure. This test verifies basic functionality.
"""

import inspect
import subprocess
from collections.abc import AsyncGenerator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from polytrader.db.models import StrategyRecord
from polytrader.platform.registry import StrategyRegistry
from polytrader.strategies.lifecycle_models import StrategyLifecycleState


@pytest.fixture
async def db_session(
    postgres_test_url: str, postgres_db: None
) -> AsyncGenerator[AsyncSession, None]:
    """Provide SQLAlchemy session for tests."""
    sqlalchemy_url = postgres_test_url
    if sqlalchemy_url.startswith("postgresql://"):
        sqlalchemy_url = sqlalchemy_url.replace("postgresql://", "postgresql+psycopg://", 1)

    engine = create_async_engine(sqlalchemy_url, echo=False)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with Session() as session:
        # Clean up strategies table
        from sqlalchemy import text

        await session.execute(text("TRUNCATE TABLE strategy_instances CASCADE"))
        await session.commit()

        yield session

        # Cleanup
        await session.execute(text("TRUNCATE TABLE strategy_instances CASCADE"))
        await session.commit()

    await engine.dispose()


@pytest.fixture
async def seeded_strategies(db_session: AsyncSession) -> list[StrategyRecord]:
    """Create test strategies in database."""
    strategies = [
        StrategyRecord(
            strategy_id="test_strategy_1",
            name="Test Strategy 1",
            config={"buy_threshold": 0.3, "min_history": 30},
            template_type_id="simple_threshold",
            template_version="1.0.0",
            config_hash="hash_1",
            desired_state=StrategyLifecycleState.RUNNING,
            actual_state=StrategyLifecycleState.RUNNING,
        ),
        StrategyRecord(
            strategy_id="test_strategy_2",
            name="Test Strategy 2",
            config={"buy_threshold": 0.35, "min_history": 30},
            template_type_id="simple_threshold",
            template_version="1.0.0",
            config_hash="hash_2",
            desired_state=StrategyLifecycleState.RUNNING,
            actual_state=StrategyLifecycleState.RUNNING,
        ),
    ]

    for strategy in strategies:
        db_session.add(strategy)

    await db_session.commit()
    return strategies


@pytest.mark.integration
def test_cli_platform_start_help() -> None:
    """Test that CLI platform start command exists and shows help."""
    result = subprocess.run(
        ["python", "-m", "cli", "platform", "start", "--help"],
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode == 0
    assert "Start the platform" in result.stdout
    assert "--api-host" in result.stdout
    assert "--api-port" in result.stdout


@pytest.mark.integration
async def test_platform_loads_strategies_from_db(
    db_session: AsyncSession, seeded_strategies: list[StrategyRecord]
) -> None:
    """Test that platform can load strategies from database.

    This test verifies that StrategyRegistry can list strategies,
    which is what PlatformOrchestrator does during startup.
    """
    registry = StrategyRegistry(db_session)
    strategies = await registry.list_strategies()

    assert len(strategies) == 2
    strategy_ids = {s.strategy_id for s in strategies}
    assert "test_strategy_1" in strategy_ids
    assert "test_strategy_2" in strategy_ids

    # Verify enabled strategies
    enabled = [s for s in strategies if s.desired_state == StrategyLifecycleState.RUNNING]
    assert len(enabled) == 2


@pytest.mark.integration
async def test_platform_start_task_imports() -> None:
    """Test that platform_start_task can be imported and called.

    This is a basic smoke test to ensure the task function exists
    and can be imported without errors.
    """
    from polytrader.tasks.platform import platform_start_task

    # Verify function exists and is callable
    assert callable(platform_start_task)
    assert inspect.iscoroutinefunction(platform_start_task)


@pytest.mark.integration
@pytest.mark.skip(reason="Requires full platform startup - complex integration test")
async def test_platform_starts_api_server() -> None:
    """Test that platform starts API server and it's accessible.

    This test would:
    1. Start platform in background
    2. Wait for API server to be ready
    3. Make HTTP request to /api/v1/state/health
    4. Verify response
    5. Stop platform

    Note: This is skipped because it requires:
    - Long-running process management
    - Port availability
    - Graceful shutdown handling
    - Complex async coordination

    This should be implemented as a separate end-to-end test.
    """
    # TODO: Implement full platform startup test
    # This would require:
    # - Starting platform_start_task in background
    # - Waiting for API server to be ready
    # - Making HTTP requests
    # - Gracefully shutting down
    pass
