"""Unit tests for market data API models.

Per Commit 1: API models for market tick data responses.
Per testing.mdc: Unit tests must be deterministic, fast, and isolated.
API model tests verify validation, serialization, and deserialization.
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from polytrader.api.models import (
    HistoricalTicksResponse,
    MarketInfoResponse,
    MarketsResponse,
    MarketTickResponse,
)


class TestMarketTickResponse:
    """Tests for MarketTickResponse model."""

    def test_market_tick_response_with_all_fields(self) -> None:
        """Test MarketTickResponse with all fields."""
        tick_id = uuid.uuid4()
        ts_wall = datetime(2025, 1, 27, 12, 0, 0, tzinfo=UTC)

        response = MarketTickResponse(
            tick_id=tick_id,
            ts_wall=ts_wall,
            ts_mono=1234567890.123456,
            market_slug="btc-updown-15m-1767900600",
            outcome="UP",
            best_bid=Decimal("0.45000000"),
            best_ask=Decimal("0.46000000"),
            mid=Decimal("0.45500000"),
            spread=Decimal("0.01000000"),
            spread_bps=Decimal("100.00"),
        )

        assert response.tick_id == tick_id
        assert response.ts_wall == ts_wall
        assert response.ts_mono == 1234567890.123456
        assert response.market_slug == "btc-updown-15m-1767900600"
        assert response.outcome == "UP"
        assert response.best_bid == Decimal("0.45000000")
        assert response.best_ask == Decimal("0.46000000")
        assert response.mid == Decimal("0.45500000")
        assert response.spread == Decimal("0.01000000")
        assert response.spread_bps == Decimal("100.00")

    @pytest.mark.parametrize(
        "best_bid,best_ask,expected_mid",
        [
            (Decimal("0.4"), Decimal("0.5"), Decimal("0.45")),
            (Decimal("0.0"), Decimal("1.0"), Decimal("0.5")),
            (Decimal("0.45"), Decimal("0.46"), Decimal("0.455")),
        ],
    )
    def test_market_tick_response_mid_value(
        self, best_bid: Decimal, best_ask: Decimal, expected_mid: Decimal
    ) -> None:
        """Test that mid price is correctly stored (not computed)."""
        tick_id = uuid.uuid4()
        ts_wall = datetime(2025, 1, 27, 12, 0, 0, tzinfo=UTC)

        response = MarketTickResponse(
            tick_id=tick_id,
            ts_wall=ts_wall,
            ts_mono=1234567890.123456,
            market_slug="btc-updown-15m-1767900600",
            outcome="UP",
            best_bid=best_bid,
            best_ask=best_ask,
            mid=expected_mid,  # Mid is provided, not computed
            spread=best_ask - best_bid,
            spread_bps=(best_ask - best_bid) * Decimal("10000"),
        )

        assert response.mid == expected_mid

    def test_market_tick_response_serialization(self) -> None:
        """Test MarketTickResponse serialization to JSON."""
        tick_id = uuid.uuid4()
        ts_wall = datetime(2025, 1, 27, 12, 0, 0, tzinfo=UTC)

        response = MarketTickResponse(
            tick_id=tick_id,
            ts_wall=ts_wall,
            ts_mono=1234567890.123456,
            market_slug="btc-updown-15m-1767900600",
            outcome="UP",
            best_bid=Decimal("0.45000000"),
            best_ask=Decimal("0.46000000"),
            mid=Decimal("0.45500000"),
            spread=Decimal("0.01000000"),
            spread_bps=Decimal("100.00"),
        )

        # Serialize to dict (Python types)
        data = response.model_dump()
        assert isinstance(data["tick_id"], uuid.UUID)
        assert isinstance(data["ts_wall"], datetime)
        assert isinstance(data["best_bid"], Decimal)
        assert isinstance(data["best_ask"], Decimal)
        assert isinstance(data["mid"], Decimal)
        assert isinstance(data["spread"], Decimal)
        assert isinstance(data["spread_bps"], Decimal)

        # Serialize to JSON-compatible dict
        json_data = response.model_dump(mode="json")
        assert isinstance(json_data["tick_id"], str)  # UUID serialized to string
        assert isinstance(json_data["ts_wall"], str)  # datetime serialized to ISO string
        assert isinstance(json_data["best_bid"], str)  # Decimal serialized to string
        assert isinstance(json_data["best_ask"], str)
        assert isinstance(json_data["mid"], str)
        assert isinstance(json_data["spread"], str)
        assert isinstance(json_data["spread_bps"], str)

    def test_market_tick_response_deserialization(self) -> None:
        """Test MarketTickResponse deserialization from dict."""
        tick_id = uuid.uuid4()
        ts_wall = datetime(2025, 1, 27, 12, 0, 0, tzinfo=UTC)

        data = {
            "tick_id": str(tick_id),
            "ts_wall": ts_wall.isoformat(),
            "ts_mono": 1234567890.123456,
            "market_slug": "btc-updown-15m-1767900600",
            "outcome": "UP",
            "best_bid": "0.45000000",
            "best_ask": "0.46000000",
            "mid": "0.45500000",
            "spread": "0.01000000",
            "spread_bps": "100.00",
        }

        response = MarketTickResponse.model_validate(data)

        assert response.tick_id == tick_id
        assert response.best_bid == Decimal("0.45000000")
        assert response.best_ask == Decimal("0.46000000")

    def test_market_tick_response_accepts_any_outcome_string(self) -> None:
        """Test that outcome field accepts any string value (no enum constraint).

        Note: Outcome validation happens at the API endpoint level, not in the model.
        The model accepts any string for flexibility.
        """
        tick_id = uuid.uuid4()
        ts_wall = datetime(2025, 1, 27, 12, 0, 0, tzinfo=UTC)

        # Outcome is just a string field, so any string is accepted
        response = MarketTickResponse(
            tick_id=tick_id,
            ts_wall=ts_wall,
            ts_mono=1234567890.123456,
            market_slug="btc-updown-15m-1767900600",
            outcome="INVALID",  # Any string is accepted
            best_bid=Decimal("0.45"),
            best_ask=Decimal("0.46"),
            mid=Decimal("0.455"),
            spread=Decimal("0.01"),
            spread_bps=Decimal("100.00"),
        )

        assert response.outcome == "INVALID"

    def test_market_tick_response_valid_outcomes(self) -> None:
        """Test that valid outcomes (UP, DOWN) work correctly."""
        tick_id = uuid.uuid4()
        ts_wall = datetime(2025, 1, 27, 12, 0, 0, tzinfo=UTC)

        for outcome in ["UP", "DOWN"]:
            response = MarketTickResponse(
                tick_id=tick_id,
                ts_wall=ts_wall,
                ts_mono=1234567890.123456,
                market_slug="btc-updown-15m-1767900600",
                outcome=outcome,
                best_bid=Decimal("0.45"),
                best_ask=Decimal("0.46"),
                mid=Decimal("0.455"),
                spread=Decimal("0.01"),
                spread_bps=Decimal("100.00"),
            )

            assert response.outcome == outcome

    @pytest.mark.parametrize(
        "best_bid,best_ask",
        [
            (Decimal("-0.1"), Decimal("0.5")),  # Negative bid
            (Decimal("0.4"), Decimal("1.1")),  # Ask > 1.0
            (Decimal("1.1"), Decimal("0.5")),  # Bid > 1.0
        ],
    )
    def test_market_tick_response_price_bounds(self, best_bid: Decimal, best_ask: Decimal) -> None:
        """Test that prices outside 0-1 range are allowed (no validation constraint).

        Note: Price bounds are enforced at the database level, not in the API model.
        The API model accepts any Decimal value for flexibility.
        """
        tick_id = uuid.uuid4()
        ts_wall = datetime(2025, 1, 27, 12, 0, 0, tzinfo=UTC)

        # Model should accept any Decimal value (validation happens at DB level)
        response = MarketTickResponse(
            tick_id=tick_id,
            ts_wall=ts_wall,
            ts_mono=1234567890.123456,
            market_slug="btc-updown-15m-1767900600",
            outcome="UP",
            best_bid=best_bid,
            best_ask=best_ask,
            mid=(best_bid + best_ask) / Decimal("2"),
            spread=best_ask - best_bid,
            spread_bps=(best_ask - best_bid) * Decimal("10000"),
        )

        assert response.best_bid == best_bid
        assert response.best_ask == best_ask


class TestHistoricalTicksResponse:
    """Tests for HistoricalTicksResponse model."""

    def test_historical_ticks_response_with_ticks(self) -> None:
        """Test HistoricalTicksResponse with list of ticks."""
        tick_id1 = uuid.uuid4()
        tick_id2 = uuid.uuid4()
        ts_wall1 = datetime(2025, 1, 27, 12, 0, 0, tzinfo=UTC)
        ts_wall2 = datetime(2025, 1, 27, 12, 1, 0, tzinfo=UTC)

        tick1 = MarketTickResponse(
            tick_id=tick_id1,
            ts_wall=ts_wall1,
            ts_mono=1234567890.123456,
            market_slug="btc-updown-15m-1767900600",
            outcome="UP",
            best_bid=Decimal("0.45"),
            best_ask=Decimal("0.46"),
            mid=Decimal("0.455"),
            spread=Decimal("0.01"),
            spread_bps=Decimal("100.00"),
        )

        tick2 = MarketTickResponse(
            tick_id=tick_id2,
            ts_wall=ts_wall2,
            ts_mono=1234567891.123456,
            market_slug="btc-updown-15m-1767900600",
            outcome="UP",
            best_bid=Decimal("0.451"),
            best_ask=Decimal("0.461"),
            mid=Decimal("0.456"),
            spread=Decimal("0.01"),
            spread_bps=Decimal("100.00"),
        )

        response = HistoricalTicksResponse(ticks=[tick1, tick2], count=2)

        assert len(response.ticks) == 2
        assert response.count == 2
        assert response.ticks[0].tick_id == tick_id1
        assert response.ticks[1].tick_id == tick_id2

    def test_historical_ticks_response_empty(self) -> None:
        """Test HistoricalTicksResponse with empty tick list."""
        response = HistoricalTicksResponse(ticks=[], count=0)

        assert len(response.ticks) == 0
        assert response.count == 0

    def test_historical_ticks_response_count_mismatch(self) -> None:
        """Test that count can differ from ticks length (no validation constraint).

        Note: Count is provided by the API, not validated against ticks length.
        This allows flexibility in how count is calculated (e.g., total available vs returned).
        """
        tick_id = uuid.uuid4()
        ts_wall = datetime(2025, 1, 27, 12, 0, 0, tzinfo=UTC)

        tick = MarketTickResponse(
            tick_id=tick_id,
            ts_wall=ts_wall,
            ts_mono=1234567890.123456,
            market_slug="btc-updown-15m-1767900600",
            outcome="UP",
            best_bid=Decimal("0.45"),
            best_ask=Decimal("0.46"),
            mid=Decimal("0.455"),
            spread=Decimal("0.01"),
            spread_bps=Decimal("100.00"),
        )

        # Count can be different from ticks length (e.g., if limit was applied)
        response = HistoricalTicksResponse(ticks=[tick], count=100)

        assert len(response.ticks) == 1
        assert response.count == 100

    def test_historical_ticks_response_serialization(self) -> None:
        """Test HistoricalTicksResponse serialization to JSON."""
        tick_id = uuid.uuid4()
        ts_wall = datetime(2025, 1, 27, 12, 0, 0, tzinfo=UTC)

        tick = MarketTickResponse(
            tick_id=tick_id,
            ts_wall=ts_wall,
            ts_mono=1234567890.123456,
            market_slug="btc-updown-15m-1767900600",
            outcome="UP",
            best_bid=Decimal("0.45"),
            best_ask=Decimal("0.46"),
            mid=Decimal("0.455"),
            spread=Decimal("0.01"),
            spread_bps=Decimal("100.00"),
        )

        response = HistoricalTicksResponse(ticks=[tick], count=1)

        data = response.model_dump()

        assert isinstance(data["ticks"], list)
        assert len(data["ticks"]) == 1
        assert data["count"] == 1
        assert isinstance(data["ticks"][0], dict)


class TestMarketInfoResponse:
    """Tests for MarketInfoResponse model."""

    def test_market_info_response_with_all_fields(self) -> None:
        """Test MarketInfoResponse with all fields."""
        ts_wall = datetime(2025, 1, 27, 12, 0, 0, tzinfo=UTC)

        response = MarketInfoResponse(
            market_slug="btc-updown-15m-1767900600",
            outcome="UP",
            latest_tick_ts=ts_wall,
            active=True,
        )

        assert response.market_slug == "btc-updown-15m-1767900600"
        assert response.outcome == "UP"
        assert response.latest_tick_ts == ts_wall
        assert response.active is True

    def test_market_info_response_with_null_timestamp(self) -> None:
        """Test MarketInfoResponse with null latest_tick_ts."""
        response = MarketInfoResponse(
            market_slug="btc-updown-15m-1767900600",
            outcome="UP",
            latest_tick_ts=None,
            active=False,
        )

        assert response.market_slug == "btc-updown-15m-1767900600"
        assert response.outcome == "UP"
        assert response.latest_tick_ts is None
        assert response.active is False

    def test_market_info_response_active_states(self) -> None:
        """Test MarketInfoResponse with different active states."""
        ts_wall = datetime(2025, 1, 27, 12, 0, 0, tzinfo=UTC)

        response_active = MarketInfoResponse(
            market_slug="btc-updown-15m-1767900600",
            outcome="UP",
            latest_tick_ts=ts_wall,
            active=True,
        )

        assert response_active.active is True

        response_inactive = MarketInfoResponse(
            market_slug="btc-updown-15m-1767899700",
            outcome="UP",
            latest_tick_ts=ts_wall,
            active=False,
        )

        assert response_inactive.active is False

    def test_market_info_response_serialization(self) -> None:
        """Test MarketInfoResponse serialization to JSON."""
        ts_wall = datetime(2025, 1, 27, 12, 0, 0, tzinfo=UTC)

        response = MarketInfoResponse(
            market_slug="btc-updown-15m-1767900600",
            outcome="UP",
            latest_tick_ts=ts_wall,
            active=True,
        )

        # Serialize to dict (Python types)
        data = response.model_dump()
        assert isinstance(data["market_slug"], str)
        assert isinstance(data["outcome"], str)
        assert isinstance(data["latest_tick_ts"], datetime)
        assert isinstance(data["active"], bool)

        # Serialize to JSON-compatible dict
        json_data = response.model_dump(mode="json")
        assert isinstance(json_data["latest_tick_ts"], str)  # datetime serialized to ISO string

    def test_market_info_response_serialization_null_timestamp(self) -> None:
        """Test MarketInfoResponse serialization with null timestamp."""
        response = MarketInfoResponse(
            market_slug="btc-updown-15m-1767900600",
            outcome="UP",
            latest_tick_ts=None,
            active=False,
        )

        data = response.model_dump()

        assert data["latest_tick_ts"] is None


class TestMarketsResponse:
    """Tests for MarketsResponse model."""

    def test_markets_response_with_markets(self) -> None:
        """Test MarketsResponse with list of markets."""
        ts_wall1 = datetime(2025, 1, 27, 12, 0, 0, tzinfo=UTC)
        ts_wall2 = datetime(2025, 1, 27, 11, 45, 0, tzinfo=UTC)

        market1 = MarketInfoResponse(
            market_slug="btc-updown-15m-1767900600",
            outcome="UP",
            latest_tick_ts=ts_wall1,
            active=True,
        )

        market2 = MarketInfoResponse(
            market_slug="btc-updown-15m-1767899700",
            outcome="UP",
            latest_tick_ts=ts_wall2,
            active=False,
        )

        response = MarketsResponse(markets=[market1, market2], count=2)

        assert len(response.markets) == 2
        assert response.count == 2
        assert response.markets[0].market_slug == "btc-updown-15m-1767900600"
        assert response.markets[1].market_slug == "btc-updown-15m-1767899700"

    def test_markets_response_empty(self) -> None:
        """Test MarketsResponse with empty market list."""
        response = MarketsResponse(markets=[], count=0)

        assert len(response.markets) == 0
        assert response.count == 0

    def test_markets_response_count_mismatch(self) -> None:
        """Test that count can differ from markets length (no validation constraint)."""
        ts_wall = datetime(2025, 1, 27, 12, 0, 0, tzinfo=UTC)

        market = MarketInfoResponse(
            market_slug="btc-updown-15m-1767900600",
            outcome="UP",
            latest_tick_ts=ts_wall,
            active=True,
        )

        # Count can be different from markets length (e.g., if filtering was applied)
        response = MarketsResponse(markets=[market], count=10)

        assert len(response.markets) == 1
        assert response.count == 10

    def test_markets_response_serialization(self) -> None:
        """Test MarketsResponse serialization to JSON."""
        ts_wall = datetime(2025, 1, 27, 12, 0, 0, tzinfo=UTC)

        market = MarketInfoResponse(
            market_slug="btc-updown-15m-1767900600",
            outcome="UP",
            latest_tick_ts=ts_wall,
            active=True,
        )

        response = MarketsResponse(markets=[market], count=1)

        data = response.model_dump()

        assert isinstance(data["markets"], list)
        assert len(data["markets"]) == 1
        assert data["count"] == 1
        assert isinstance(data["markets"][0], dict)
