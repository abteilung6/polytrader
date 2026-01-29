"""Unit tests for API dependency functions.

Per Commit 2: Dependency injection functions for market data API.
Per testing.mdc: Unit tests must be deterministic, fast, and isolated.
Dependency tests verify that dependencies return correct types.
"""

from unittest.mock import AsyncMock

from sqlalchemy.ext.asyncio import AsyncSession

from polytrader.api.dependencies import get_market_tick_repository
from polytrader.db.repository import MarketTickRepository


class TestGetMarketTickRepository:
    """Tests for get_market_tick_repository dependency function."""

    def test_get_market_tick_repository_returns_correct_type(self) -> None:
        """Test that get_market_tick_repository returns MarketTickRepository."""
        # Create a mock session
        mock_session = AsyncMock(spec=AsyncSession)

        # Call the dependency function
        repo = get_market_tick_repository(session=mock_session)

        # Verify it returns the correct type
        assert isinstance(repo, MarketTickRepository)
        assert repo.session is mock_session

    def test_get_market_tick_repository_uses_provided_session(self) -> None:
        """Test that get_market_tick_repository uses the provided session."""
        # Create a mock session
        mock_session = AsyncMock(spec=AsyncSession)

        # Call the dependency function
        repo = get_market_tick_repository(session=mock_session)

        # Verify the repository uses the provided session
        assert repo.session is mock_session

    def test_get_market_tick_repository_creates_new_instance(self) -> None:
        """Test that get_market_tick_repository creates a new instance each time."""
        # Create a mock session
        mock_session = AsyncMock(spec=AsyncSession)

        # Call the dependency function twice
        repo1 = get_market_tick_repository(session=mock_session)
        repo2 = get_market_tick_repository(session=mock_session)

        # Verify they are different instances (but use same session)
        assert repo1 is not repo2
        assert repo1.session is mock_session
        assert repo2.session is mock_session
