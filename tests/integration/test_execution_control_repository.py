"""Integration tests for ExecutionControlRepository.

Tests verify that ExecutionControlRepository provides correct operations
for execution control singleton using real database.
"""

from collections.abc import AsyncGenerator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from polytrader.platform.control import ExecutionControlRepository


@pytest.fixture
async def db_session(
    postgres_test_url: str, postgres_db: None
) -> AsyncGenerator[AsyncSession, None]:
    """Provide SQLAlchemy session for tests."""
    # Convert URL to SQLAlchemy async format
    sqlalchemy_url = postgres_test_url
    if sqlalchemy_url.startswith("postgresql://"):
        sqlalchemy_url = sqlalchemy_url.replace("postgresql://", "postgresql+psycopg://", 1)

    # Create engine and session
    engine = create_async_engine(sqlalchemy_url, echo=False)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with Session() as session:
        yield session

    await engine.dispose()


@pytest.fixture
async def repository(db_session: AsyncSession) -> ExecutionControlRepository:
    """Create ExecutionControlRepository for testing."""
    return ExecutionControlRepository(db_session)


class TestGetControl:
    """Test get_control() method."""

    @pytest.mark.asyncio
    async def test_get_control_returns_singleton_with_version_one(
        self, repository: ExecutionControlRepository
    ) -> None:
        """Test that get_control() returns singleton with version=1 initially."""
        control = await repository.get_control()

        assert control.id == 1
        assert control.execution_enabled is False
        assert control.version == 1
        assert control.updated_by == "system"
        assert "Initial state" in control.reason


class TestUpdateControl:
    """Test update_control() method."""

    @pytest.mark.asyncio
    async def test_update_control_increments_version(
        self, repository: ExecutionControlRepository
    ) -> None:
        """Test that update_control() increments version (1 → 2 → 3)."""
        # First update
        updated1 = await repository.update_control(
            execution_enabled=True,
            updated_by="operator",
            reason="Enable for testing",
        )
        assert updated1.version == 2
        assert updated1.execution_enabled is True

        # Second update
        updated2 = await repository.update_control(
            execution_enabled=False,
            updated_by="operator",
            reason="Disable after testing",
        )
        assert updated2.version == 3
        assert updated2.execution_enabled is False

    @pytest.mark.asyncio
    async def test_update_control_returns_updated_record(
        self, repository: ExecutionControlRepository
    ) -> None:
        """Test that update_control() returns updated record with new version."""
        updated = await repository.update_control(
            execution_enabled=True,
            updated_by="test_user",
            reason="Test update",
        )

        assert updated.execution_enabled is True
        assert updated.updated_by == "test_user"
        assert updated.reason == "Test update"
        assert updated.version >= 2  # Version should be incremented

    @pytest.mark.asyncio
    async def test_update_control_version_persists_across_instances(
        self, db_session: AsyncSession
    ) -> None:
        """Test that version persists across repository instances."""
        repo1 = ExecutionControlRepository(db_session)
        updated1 = await repo1.update_control(
            execution_enabled=True,
            updated_by="user1",
            reason="First update",
        )
        version_after_first = updated1.version

        # Create new repository instance
        repo2 = ExecutionControlRepository(db_session)
        control = await repo2.get_control()
        assert control.version == version_after_first

        # Update with second instance
        updated2 = await repo2.update_control(
            execution_enabled=False,
            updated_by="user2",
            reason="Second update",
        )
        assert updated2.version == version_after_first + 1
