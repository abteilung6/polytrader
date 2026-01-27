"""Unit tests for market data API endpoints.

Per Commit 3: GET /api/v1/market/ticks/latest endpoint.
Per testing.mdc: Unit tests must be deterministic, fast, and isolated.
API endpoint tests verify parameter validation and response formatting.
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from polytrader.api.app import create_app
from polytrader.api.dependencies import get_market_tick_repository
from polytrader.api.models import MarketTickResponse
from polytrader.db.models import MarketTickRecord
from polytrader.db.repository import MarketTickRepository


@pytest.fixture
def mock_repository() -> MagicMock:
    """Create a mock MarketTickRepository."""
    return MagicMock(spec=MarketTickRepository)


@pytest.fixture
def client(mock_repository: MagicMock) -> TestClient:
    """Create FastAPI test client with mocked repository."""
    app = create_app()

    # Override dependency to use mock repository
    def override_get_market_tick_repository() -> MagicMock:
        return mock_repository

    app.dependency_overrides[get_market_tick_repository] = override_get_market_tick_repository

    return TestClient(app)


class TestGetLatestTickEndpoint:
    """Tests for GET /api/v1/market/ticks/latest endpoint."""

    def test_missing_market_slug_parameter(self, client: TestClient) -> None:
        """Test that missing market_slug parameter returns 422 (validation error)."""
        response = client.get("/api/v1/market/ticks/latest", params={"outcome": "UP"})

        assert response.status_code == 422  # FastAPI validation error
        data = response.json()
        assert "detail" in data

    def test_missing_outcome_parameter(self, client: TestClient) -> None:
        """Test that missing outcome parameter returns 422 (validation error)."""
        response = client.get(
            "/api/v1/market/ticks/latest",
            params={"market_slug": "btc-updown-15m-1767900600"},
        )

        assert response.status_code == 422  # FastAPI validation error
        data = response.json()
        assert "detail" in data

    def test_invalid_outcome_value(self, client: TestClient, mock_repository: MagicMock) -> None:
        """Test that invalid outcome value returns 400."""
        response = client.get(
            "/api/v1/market/ticks/latest",
            params={"market_slug": "btc-updown-15m-1767900600", "outcome": "INVALID"},
        )

        assert response.status_code == 400
        data = response.json()
        assert "detail" in data
        detail = data["detail"]
        assert detail["error"] == "Invalid outcome"
        assert detail["code"] == "INVALID_OUTCOME"

        # Verify repository was not called
        mock_repository.get_latest.assert_not_called()

    def test_valid_outcome_up(self, client: TestClient, mock_repository: MagicMock) -> None:
        """Test that valid outcome 'UP' is accepted."""
        tick_id = uuid.uuid4()
        ts_wall = datetime(2025, 1, 27, 12, 0, 0, tzinfo=UTC)

        # Create mock record
        mock_record = MagicMock(spec=MarketTickRecord)
        mock_record.tick_id = tick_id
        mock_record.ts_wall = ts_wall
        mock_record.ts_mono = 1234567890.123456
        mock_record.market_slug = "btc-updown-15m-1767900600"
        mock_record.outcome = "UP"
        mock_record.best_bid = Decimal("0.45000000")
        mock_record.best_ask = Decimal("0.46000000")
        mock_record.mid = Decimal("0.45500000")
        mock_record.spread = Decimal("0.01000000")
        mock_record.spread_bps = Decimal("100.00")

        # Configure mock repository
        mock_repository.get_latest = AsyncMock(return_value=mock_record)

        response = client.get(
            "/api/v1/market/ticks/latest",
            params={"market_slug": "btc-updown-15m-1767900600", "outcome": "UP"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["market_slug"] == "btc-updown-15m-1767900600"
        assert data["outcome"] == "UP"

        # Verify repository was called with correct parameters
        mock_repository.get_latest.assert_called_once_with("btc-updown-15m-1767900600", "UP")

    def test_valid_outcome_down(self, client: TestClient, mock_repository: MagicMock) -> None:
        """Test that valid outcome 'DOWN' is accepted."""
        tick_id = uuid.uuid4()
        ts_wall = datetime(2025, 1, 27, 12, 0, 0, tzinfo=UTC)

        # Create mock record
        mock_record = MagicMock(spec=MarketTickRecord)
        mock_record.tick_id = tick_id
        mock_record.ts_wall = ts_wall
        mock_record.ts_mono = 1234567890.123456
        mock_record.market_slug = "btc-updown-15m-1767900600"
        mock_record.outcome = "DOWN"
        mock_record.best_bid = Decimal("0.45000000")
        mock_record.best_ask = Decimal("0.46000000")
        mock_record.mid = Decimal("0.45500000")
        mock_record.spread = Decimal("0.01000000")
        mock_record.spread_bps = Decimal("100.00")

        # Configure mock repository
        mock_repository.get_latest = AsyncMock(return_value=mock_record)

        response = client.get(
            "/api/v1/market/ticks/latest",
            params={"market_slug": "btc-updown-15m-1767900600", "outcome": "DOWN"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["outcome"] == "DOWN"

    def test_market_not_found_returns_404(
        self, client: TestClient, mock_repository: MagicMock
    ) -> None:
        """Test that market not found returns 404."""
        # Configure mock repository to return None
        mock_repository.get_latest = AsyncMock(return_value=None)

        response = client.get(
            "/api/v1/market/ticks/latest",
            params={"market_slug": "nonexistent-market", "outcome": "UP"},
        )

        assert response.status_code == 404
        data = response.json()
        assert "detail" in data
        detail = data["detail"]
        assert detail["error"] == "Market not found"
        assert detail["code"] == "MARKET_NOT_FOUND"

        # Verify repository was called
        mock_repository.get_latest.assert_called_once_with("nonexistent-market", "UP")

    def test_successful_response_format(
        self, client: TestClient, mock_repository: MagicMock
    ) -> None:
        """Test that successful response has correct format."""
        tick_id = uuid.uuid4()
        ts_wall = datetime(2025, 1, 27, 12, 0, 0, tzinfo=UTC)

        # Create mock record
        mock_record = MagicMock(spec=MarketTickRecord)
        mock_record.tick_id = tick_id
        mock_record.ts_wall = ts_wall
        mock_record.ts_mono = 1234567890.123456
        mock_record.market_slug = "btc-updown-15m-1767900600"
        mock_record.outcome = "UP"
        mock_record.best_bid = Decimal("0.45000000")
        mock_record.best_ask = Decimal("0.46000000")
        mock_record.mid = Decimal("0.45500000")
        mock_record.spread = Decimal("0.01000000")
        mock_record.spread_bps = Decimal("100.00")

        # Configure mock repository
        mock_repository.get_latest = AsyncMock(return_value=mock_record)

        response = client.get(
            "/api/v1/market/ticks/latest",
            params={"market_slug": "btc-updown-15m-1767900600", "outcome": "UP"},
        )

        assert response.status_code == 200
        data = response.json()

        # Verify all required fields are present
        assert "tick_id" in data
        assert "ts_wall" in data
        assert "ts_mono" in data
        assert "market_slug" in data
        assert "outcome" in data
        assert "best_bid" in data
        assert "best_ask" in data
        assert "mid" in data
        assert "spread" in data
        assert "spread_bps" in data

        # Verify response matches MarketTickResponse model
        MarketTickResponse(**data)  # Should not raise

    def test_database_error_returns_500(
        self, client: TestClient, mock_repository: MagicMock
    ) -> None:
        """Test that database error returns 500."""
        # Configure mock repository to raise exception
        mock_repository.get_latest = AsyncMock(side_effect=Exception("Database connection failed"))

        response = client.get(
            "/api/v1/market/ticks/latest",
            params={"market_slug": "btc-updown-15m-1767900600", "outcome": "UP"},
        )

        assert response.status_code == 500
        data = response.json()
        assert "detail" in data
        detail = data["detail"]
        assert detail["error"] == "Internal server error"
        assert detail["code"] == "DATABASE_ERROR"
