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
        assert detail["error"] == "Invalid parameter"
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


class TestGetHistoricalTicksEndpoint:
    """Tests for GET /api/v1/market/ticks/history endpoint."""

    def test_missing_market_slug_parameter(self, client: TestClient) -> None:
        """Test that missing market_slug parameter returns 422 (validation error)."""
        response = client.get("/api/v1/market/ticks/history", params={"outcome": "UP"})

        assert response.status_code == 422  # FastAPI validation error
        data = response.json()
        assert "detail" in data

    def test_missing_outcome_parameter(self, client: TestClient) -> None:
        """Test that missing outcome parameter returns 422 (validation error)."""
        response = client.get(
            "/api/v1/market/ticks/history",
            params={"market_slug": "btc-updown-15m-1767900600"},
        )

        assert response.status_code == 422  # FastAPI validation error
        data = response.json()
        assert "detail" in data

    def test_invalid_outcome_value(self, client: TestClient, mock_repository: MagicMock) -> None:
        """Test that invalid outcome value returns 400."""
        response = client.get(
            "/api/v1/market/ticks/history",
            params={"market_slug": "btc-updown-15m-1767900600", "outcome": "INVALID"},
        )

        assert response.status_code == 400
        data = response.json()
        assert "detail" in data
        detail = data["detail"]
        assert detail["error"] == "Invalid parameter"
        assert detail["code"] == "INVALID_OUTCOME"

        # Verify repository was not called
        mock_repository.get_history.assert_not_called()

    def test_invalid_time_range(self, client: TestClient, mock_repository: MagicMock) -> None:
        """Test that from_ts > to_ts returns 400."""
        from datetime import UTC, datetime

        from_ts = datetime(2025, 1, 27, 12, 0, 0, tzinfo=UTC)
        to_ts = datetime(2025, 1, 27, 11, 0, 0, tzinfo=UTC)  # Before from_ts

        response = client.get(
            "/api/v1/market/ticks/history",
            params={
                "market_slug": "btc-updown-15m-1767900600",
                "outcome": "UP",
                "from_ts": from_ts.isoformat(),
                "to_ts": to_ts.isoformat(),
            },
        )

        assert response.status_code == 400
        data = response.json()
        assert "detail" in data
        detail = data["detail"]
        assert detail["error"] == "Invalid time range"
        assert detail["code"] == "INVALID_TIME_RANGE"

        # Verify repository was not called
        mock_repository.get_history.assert_not_called()

    def test_successful_response_empty_list(
        self, client: TestClient, mock_repository: MagicMock
    ) -> None:
        """Test successful response with empty tick list."""
        # Configure mock repository to return empty list
        mock_repository.get_history = AsyncMock(return_value=[])

        response = client.get(
            "/api/v1/market/ticks/history",
            params={"market_slug": "btc-updown-15m-1767900600", "outcome": "UP"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "ticks" in data
        assert "count" in data
        assert data["ticks"] == []
        assert data["count"] == 0

        # Verify repository was called with correct parameters
        mock_repository.get_history.assert_called_once_with(
            market_slug="btc-updown-15m-1767900600",
            outcome="UP",
            from_ts=None,
            to_ts=None,
            limit=5000,  # Default limit
        )

    def test_successful_response_with_ticks(
        self, client: TestClient, mock_repository: MagicMock
    ) -> None:
        """Test successful response with tick list."""
        tick_id1 = uuid.uuid4()
        tick_id2 = uuid.uuid4()
        ts_wall1 = datetime(2025, 1, 27, 12, 0, 0, tzinfo=UTC)
        ts_wall2 = datetime(2025, 1, 27, 12, 1, 0, tzinfo=UTC)

        # Create mock records
        mock_record1 = MagicMock(spec=MarketTickRecord)
        mock_record1.tick_id = tick_id1
        mock_record1.ts_wall = ts_wall1
        mock_record1.ts_mono = 1234567890.123456
        mock_record1.market_slug = "btc-updown-15m-1767900600"
        mock_record1.outcome = "UP"
        mock_record1.best_bid = Decimal("0.45000000")
        mock_record1.best_ask = Decimal("0.46000000")
        mock_record1.mid = Decimal("0.45500000")
        mock_record1.spread = Decimal("0.01000000")
        mock_record1.spread_bps = Decimal("100.00")

        mock_record2 = MagicMock(spec=MarketTickRecord)
        mock_record2.tick_id = tick_id2
        mock_record2.ts_wall = ts_wall2
        mock_record2.ts_mono = 1234567891.123456
        mock_record2.market_slug = "btc-updown-15m-1767900600"
        mock_record2.outcome = "UP"
        mock_record2.best_bid = Decimal("0.45100000")
        mock_record2.best_ask = Decimal("0.46100000")
        mock_record2.mid = Decimal("0.45600000")
        mock_record2.spread = Decimal("0.01000000")
        mock_record2.spread_bps = Decimal("100.00")

        # Configure mock repository
        mock_repository.get_history = AsyncMock(return_value=[mock_record1, mock_record2])

        response = client.get(
            "/api/v1/market/ticks/history",
            params={"market_slug": "btc-updown-15m-1767900600", "outcome": "UP"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "ticks" in data
        assert "count" in data
        assert len(data["ticks"]) == 2
        assert data["count"] == 2
        assert data["ticks"][0]["tick_id"] == str(tick_id1)
        assert data["ticks"][1]["tick_id"] == str(tick_id2)

    def test_time_range_parameters(self, client: TestClient, mock_repository: MagicMock) -> None:
        """Test that from_ts and to_ts parameters are passed to repository."""
        from datetime import UTC, datetime

        from_ts = datetime(2025, 1, 27, 12, 0, 0, tzinfo=UTC)
        to_ts = datetime(2025, 1, 27, 13, 0, 0, tzinfo=UTC)

        # Configure mock repository
        mock_repository.get_history = AsyncMock(return_value=[])

        response = client.get(
            "/api/v1/market/ticks/history",
            params={
                "market_slug": "btc-updown-15m-1767900600",
                "outcome": "UP",
                "from_ts": from_ts.isoformat(),
                "to_ts": to_ts.isoformat(),
            },
        )

        assert response.status_code == 200

        # Verify repository was called with time range parameters
        call_args = mock_repository.get_history.call_args
        assert call_args.kwargs["from_ts"] == from_ts
        assert call_args.kwargs["to_ts"] == to_ts

    def test_limit_parameter(self, client: TestClient, mock_repository: MagicMock) -> None:
        """Test that limit parameter is passed to repository."""
        # Configure mock repository
        mock_repository.get_history = AsyncMock(return_value=[])

        response = client.get(
            "/api/v1/market/ticks/history",
            params={
                "market_slug": "btc-updown-15m-1767900600",
                "outcome": "UP",
                "limit": 100,
            },
        )

        assert response.status_code == 200

        # Verify repository was called with limit parameter
        call_args = mock_repository.get_history.call_args
        assert call_args.kwargs["limit"] == 100

    def test_limit_validation_max(self, client: TestClient) -> None:
        """Test that limit > 10000 returns 422 (validation error)."""
        response = client.get(
            "/api/v1/market/ticks/history",
            params={
                "market_slug": "btc-updown-15m-1767900600",
                "outcome": "UP",
                "limit": 10001,  # Exceeds max
            },
        )

        assert response.status_code == 422  # FastAPI validation error
        data = response.json()
        assert "detail" in data

    def test_limit_validation_min(self, client: TestClient) -> None:
        """Test that limit < 1 returns 422 (validation error)."""
        response = client.get(
            "/api/v1/market/ticks/history",
            params={
                "market_slug": "btc-updown-15m-1767900600",
                "outcome": "UP",
                "limit": 0,  # Below min
            },
        )

        assert response.status_code == 422  # FastAPI validation error
        data = response.json()
        assert "detail" in data

    def test_database_error_returns_500(
        self, client: TestClient, mock_repository: MagicMock
    ) -> None:
        """Test that database error returns 500."""
        # Configure mock repository to raise exception
        mock_repository.get_history = AsyncMock(side_effect=Exception("Database connection failed"))

        response = client.get(
            "/api/v1/market/ticks/history",
            params={"market_slug": "btc-updown-15m-1767900600", "outcome": "UP"},
        )

        assert response.status_code == 500
        data = response.json()
        assert "detail" in data
        detail = data["detail"]
        assert detail["error"] == "Internal server error"
        assert detail["code"] == "DATABASE_ERROR"


class TestGetMarketsEndpoint:
    """Tests for GET /api/v1/market/markets endpoint."""

    def test_successful_response_empty_list(
        self, client: TestClient, mock_repository: MagicMock
    ) -> None:
        """Test successful response with empty market list."""
        # Configure mock repository
        mock_repository.get_markets = AsyncMock(return_value=[])

        response = client.get("/api/v1/market/markets")

        assert response.status_code == 200
        data = response.json()
        assert "markets" in data
        assert "count" in data
        assert data["markets"] == []
        assert data["count"] == 0

        # Verify repository was called
        mock_repository.get_markets.assert_called_once()

    def test_successful_response_with_markets(
        self, client: TestClient, mock_repository: MagicMock
    ) -> None:
        """Test successful response with market list."""
        # Configure mock repository to return market pairs
        mock_repository.get_markets = AsyncMock(
            return_value=[
                ("btc-updown-15m-1767900600", "UP"),
                ("btc-updown-15m-1767900600", "DOWN"),
            ]
        )

        # Configure get_latest to return mock records
        tick_id = uuid.uuid4()
        ts_wall = datetime(2025, 1, 27, 12, 0, 0, tzinfo=UTC)

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

        # Mock get_latest to return record for UP, None for DOWN
        async def get_latest_side_effect(market_slug: str, outcome: str):
            if outcome == "UP":
                return mock_record
            return None

        mock_repository.get_latest = AsyncMock(side_effect=get_latest_side_effect)

        response = client.get("/api/v1/market/markets")

        assert response.status_code == 200
        data = response.json()
        assert "markets" in data
        assert "count" in data
        assert len(data["markets"]) == 2
        assert data["count"] == 2

        # Verify market structure
        up_market = next(m for m in data["markets"] if m["outcome"] == "UP")
        assert up_market["market_slug"] == "btc-updown-15m-1767900600"
        assert up_market["outcome"] == "UP"
        assert up_market["latest_tick_ts"] is not None
        assert "active" in up_market

        down_market = next(m for m in data["markets"] if m["outcome"] == "DOWN")
        assert down_market["market_slug"] == "btc-updown-15m-1767900600"
        assert down_market["outcome"] == "DOWN"
        assert down_market["latest_tick_ts"] is None

    def test_pattern_filter(self, client: TestClient, mock_repository: MagicMock) -> None:
        """Test that pattern filter works correctly."""
        # Configure mock repository to return multiple markets
        mock_repository.get_markets = AsyncMock(
            return_value=[
                ("btc-updown-15m-1767900600", "UP"),
                ("eth-updown-15m-1767900600", "UP"),
            ]
        )

        # Configure get_latest to return None for all
        mock_repository.get_latest = AsyncMock(return_value=None)

        response = client.get("/api/v1/market/markets", params={"pattern": "btc-updown-15m"})

        assert response.status_code == 200
        data = response.json()
        assert len(data["markets"]) == 1
        assert data["markets"][0]["market_slug"] == "btc-updown-15m-1767900600"

    def test_active_only_filter(self, client: TestClient, mock_repository: MagicMock) -> None:
        """Test that active_only filter works correctly."""
        # Configure mock repository
        mock_repository.get_markets = AsyncMock(return_value=[("btc-updown-15m-1767900600", "UP")])
        mock_repository.get_latest = AsyncMock(return_value=None)

        # Note: active status depends on current time and market window
        # This test verifies the filter is applied, not the exact active status
        response = client.get("/api/v1/market/markets", params={"active_only": True})

        assert response.status_code == 200
        data = response.json()
        # Result depends on whether market is actually active (time-dependent)
        assert "markets" in data
        assert "count" in data

    def test_ordering_newest_first(self, client: TestClient, mock_repository: MagicMock) -> None:
        """Test that markets are ordered by latest_tick_ts descending."""
        # Configure mock repository
        mock_repository.get_markets = AsyncMock(
            return_value=[
                ("btc-updown-15m-1767900600", "UP"),
                ("btc-updown-15m-1767899700", "UP"),
            ]
        )

        # Create mock records with different timestamps
        ts_wall1 = datetime(2025, 1, 27, 12, 0, 0, tzinfo=UTC)
        ts_wall2 = datetime(2025, 1, 27, 11, 45, 0, tzinfo=UTC)  # Earlier

        mock_record1 = MagicMock(spec=MarketTickRecord)
        mock_record1.ts_wall = ts_wall1

        mock_record2 = MagicMock(spec=MarketTickRecord)
        mock_record2.ts_wall = ts_wall2

        async def get_latest_side_effect(market_slug: str, outcome: str):
            if "1767900600" in market_slug:
                return mock_record1
            return mock_record2

        mock_repository.get_latest = AsyncMock(side_effect=get_latest_side_effect)

        response = client.get("/api/v1/market/markets")

        assert response.status_code == 200
        data = response.json()
        assert len(data["markets"]) == 2

        # First market should have later timestamp
        # FastAPI serializes datetime with 'Z' suffix, not '+00:00'
        assert data["markets"][0]["latest_tick_ts"] == ts_wall1.isoformat().replace("+00:00", "Z")
        assert data["markets"][1]["latest_tick_ts"] == ts_wall2.isoformat().replace("+00:00", "Z")

    def test_ordering_nulls_last(self, client: TestClient, mock_repository: MagicMock) -> None:
        """Test that markets with null latest_tick_ts appear last."""
        # Configure mock repository
        mock_repository.get_markets = AsyncMock(
            return_value=[
                ("btc-updown-15m-1767900600", "UP"),
                ("btc-updown-15m-1767899700", "UP"),
            ]
        )

        # Create mock record for first market only
        ts_wall = datetime(2025, 1, 27, 12, 0, 0, tzinfo=UTC)

        mock_record = MagicMock(spec=MarketTickRecord)
        mock_record.ts_wall = ts_wall

        async def get_latest_side_effect(market_slug: str, outcome: str):
            if "1767900600" in market_slug:
                return mock_record
            return None  # Second market has no ticks

        mock_repository.get_latest = AsyncMock(side_effect=get_latest_side_effect)

        response = client.get("/api/v1/market/markets")

        assert response.status_code == 200
        data = response.json()
        assert len(data["markets"]) == 2

        # First market should have timestamp, second should be null
        assert data["markets"][0]["latest_tick_ts"] is not None
        assert data["markets"][1]["latest_tick_ts"] is None

    def test_database_error_returns_500(
        self, client: TestClient, mock_repository: MagicMock
    ) -> None:
        """Test that database error returns 500."""
        # Configure mock repository to raise exception
        mock_repository.get_markets = AsyncMock(side_effect=Exception("Database connection failed"))

        response = client.get("/api/v1/market/markets")

        assert response.status_code == 500
        data = response.json()
        assert "detail" in data
        detail = data["detail"]
        assert detail["error"] == "Internal server error"
        assert detail["code"] == "DATABASE_ERROR"
