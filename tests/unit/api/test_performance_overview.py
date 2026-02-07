"""Unit tests for GET /api/v1/state/strategies/performance/overview.

Per PERFORMANCE_OVERVIEW_PROPOSAL.md §7 and testing.mdc:
- Verifies response schema, evidence tier, query params.
- Uses mocked PerformanceOverviewRepository (no DB).
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from polytrader.api.app import create_app
from polytrader.api.dependencies import get_performance_overview_repo
from polytrader.db.performance_repository import (
    PerformanceOverviewItem,
    PerformanceOverviewRepository,
)

ENDPOINT = "/api/v1/state/strategies/performance/overview"


def _make_item(
    strategy_id: str = "strat-1",
    trade_count: int = 5,
    total_realized_pnl: float = 10.0,
    evidence_tier: str = "TRACKING",
) -> PerformanceOverviewItem:
    """Factory for PerformanceOverviewItem."""
    return PerformanceOverviewItem(
        strategy_id=strategy_id,
        name="Test Strategy",
        template_type_id="vfmr",
        template_version="1.0.0",
        actual_state="RUNNING",
        trade_count=trade_count,
        wins=3,
        losses=1,
        breakevens=1,
        total_realized_pnl=total_realized_pnl,
        avg_trade_pnl=2.0,
        win_rate_pct=60.0,
        profit_factor=3.0,
        last_trade_exit_ts_wall=datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC),
        evidence_tier=evidence_tier,
    )


@pytest.fixture
def mock_repo() -> MagicMock:
    """Create a mock PerformanceOverviewRepository."""
    repo = MagicMock(spec=PerformanceOverviewRepository)
    repo.get_overview = AsyncMock(return_value=[])
    return repo


@pytest.fixture
def client(mock_repo: MagicMock) -> TestClient:
    """Create FastAPI test client with mocked repo."""
    app = create_app()

    def override() -> MagicMock:
        return mock_repo

    app.dependency_overrides[get_performance_overview_repo] = override
    return TestClient(app)


class TestPerformanceOverviewEndpoint:
    """Tests for GET /api/v1/state/strategies/performance/overview."""

    def test_empty_response(self, client: TestClient, mock_repo: MagicMock) -> None:
        """Empty overview returns 200 with empty items list."""
        mock_repo.get_overview = AsyncMock(return_value=[])

        response = client.get(ENDPOINT)

        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["min_trades_threshold"] >= 1

    def test_response_includes_items(self, client: TestClient, mock_repo: MagicMock) -> None:
        """Response includes PerformanceOverviewItemResponse for each item."""
        mock_repo.get_overview = AsyncMock(
            return_value=[
                _make_item(strategy_id="s1", total_realized_pnl=50.0),
                _make_item(strategy_id="s2", total_realized_pnl=10.0),
            ]
        )

        response = client.get(ENDPOINT)

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 2
        assert data["items"][0]["strategy_id"] == "s1"
        assert data["items"][0]["total_realized_pnl"] == 50.0
        assert data["items"][1]["strategy_id"] == "s2"

    def test_response_includes_resolved_timestamps(
        self, client: TestClient, mock_repo: MagicMock
    ) -> None:
        """Response includes from_ts_wall and to_ts_wall."""
        mock_repo.get_overview = AsyncMock(return_value=[])

        response = client.get(
            ENDPOINT,
            params={"since": "2026-01-01T00:00:00Z", "until": "2026-02-01T00:00:00Z"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["from_ts_wall"] is not None
        assert data["to_ts_wall"] is not None

    def test_from_ts_wall_null_for_all_time(self, client: TestClient, mock_repo: MagicMock) -> None:
        """from_ts_wall is null when 'since' is not provided (all time)."""
        mock_repo.get_overview = AsyncMock(return_value=[])

        response = client.get(ENDPOINT)

        assert response.status_code == 200
        data = response.json()
        assert data["from_ts_wall"] is None

    def test_evidence_tier_in_response(self, client: TestClient, mock_repo: MagicMock) -> None:
        """Each item includes evidence_tier field."""
        mock_repo.get_overview = AsyncMock(
            return_value=[
                _make_item(evidence_tier="TRACKING"),
                _make_item(strategy_id="s2", evidence_tier="INSUFFICIENT_DATA"),
            ]
        )

        response = client.get(ENDPOINT)

        assert response.status_code == 200
        data = response.json()
        assert data["items"][0]["evidence_tier"] == "TRACKING"
        assert data["items"][1]["evidence_tier"] == "INSUFFICIENT_DATA"

    def test_query_params_passed_to_repo(self, client: TestClient, mock_repo: MagicMock) -> None:
        """Query parameters are forwarded to the repository."""
        mock_repo.get_overview = AsyncMock(return_value=[])

        response = client.get(
            ENDPOINT,
            params={
                "execution_mode": "paper",
                "template_type_id": "vfmr",
                "state": "RUNNING",
                "sort_by": "trade_count",
                "limit": 50,
            },
        )

        assert response.status_code == 200
        mock_repo.get_overview.assert_awaited_once()
        call_kwargs = mock_repo.get_overview.call_args.kwargs
        assert call_kwargs["execution_mode"] == "paper"
        assert call_kwargs["template_type_id"] == "vfmr"
        assert call_kwargs["state"] == "RUNNING"
        assert call_kwargs["sort_by"] == "trade_count"
        assert call_kwargs["limit"] == 50

    def test_execution_mode_echoed_in_response(
        self, client: TestClient, mock_repo: MagicMock
    ) -> None:
        """execution_mode filter is echoed in the response."""
        mock_repo.get_overview = AsyncMock(return_value=[])

        response = client.get(ENDPOINT, params={"execution_mode": "live"})

        assert response.status_code == 200
        data = response.json()
        assert data["execution_mode"] == "live"

    def test_execution_mode_null_when_not_filtered(
        self, client: TestClient, mock_repo: MagicMock
    ) -> None:
        """execution_mode is null when no filter is applied."""
        mock_repo.get_overview = AsyncMock(return_value=[])

        response = client.get(ENDPOINT)

        assert response.status_code == 200
        data = response.json()
        assert data["execution_mode"] is None

    def test_invalid_execution_mode_returns_422(
        self, client: TestClient, mock_repo: MagicMock
    ) -> None:
        """Invalid execution_mode returns 422 validation error."""
        response = client.get(ENDPOINT, params={"execution_mode": "invalid"})

        assert response.status_code == 422

    def test_item_fields_complete(self, client: TestClient, mock_repo: MagicMock) -> None:
        """Verify all expected fields are present in a response item."""
        mock_repo.get_overview = AsyncMock(return_value=[_make_item()])

        response = client.get(ENDPOINT)

        assert response.status_code == 200
        item = response.json()["items"][0]
        expected_fields = {
            "strategy_id",
            "name",
            "template_type_id",
            "template_version",
            "actual_state",
            "trade_count",
            "wins",
            "losses",
            "breakevens",
            "total_realized_pnl",
            "avg_trade_pnl",
            "win_rate_pct",
            "profit_factor",
            "last_trade_exit_ts_wall",
            "evidence_tier",
        }
        assert expected_fields.issubset(set(item.keys()))
