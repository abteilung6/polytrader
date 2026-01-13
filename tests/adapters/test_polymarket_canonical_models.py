"""Tests for canonical user stream event models.

Per Phase 6 Commit 2: Canonical models normalize venue WebSocket messages.
"""

import pytest
from pydantic import ValidationError

from polytrader.adapters.polymarket.models import (
    CanonicalCancel,
    CanonicalFill,
    CanonicalOrderAck,
    CanonicalOrderReject,
)


class TestCanonicalOrderAck:
    """Tests for CanonicalOrderAck model."""

    def test_canonical_order_ack_creation(self) -> None:
        """Test that CanonicalOrderAck can be created."""
        ack = CanonicalOrderAck(
            client_order_id="client-123",
            venue_order_id="venue-456",
            timestamp="2024-01-15T10:30:45.123456Z",
        )

        assert ack.client_order_id == "client-123"
        assert ack.venue_order_id == "venue-456"
        assert ack.timestamp == "2024-01-15T10:30:45.123456Z"

    def test_canonical_order_ack_required_fields(self) -> None:
        """Test that all fields are required."""
        with pytest.raises(ValidationError):
            CanonicalOrderAck()  # type: ignore

        with pytest.raises(ValidationError):
            CanonicalOrderAck(
                client_order_id="client-123"
                # Missing venue_order_id and timestamp
            )  # type: ignore

    def test_canonical_order_ack_serialization(self) -> None:
        """Test that CanonicalOrderAck can be serialized."""
        ack = CanonicalOrderAck(
            client_order_id="client-123",
            venue_order_id="venue-456",
            timestamp="2024-01-15T10:30:45Z",
        )

        # Pydantic model can be serialized
        ack_dict = ack.model_dump()
        assert ack_dict["client_order_id"] == "client-123"
        assert ack_dict["venue_order_id"] == "venue-456"

        # JSON serialization
        ack_json = ack.model_dump_json()
        assert isinstance(ack_json, str)
        assert "client-123" in ack_json


class TestCanonicalOrderReject:
    """Tests for CanonicalOrderReject model."""

    def test_canonical_order_reject_creation(self) -> None:
        """Test that CanonicalOrderReject can be created."""
        reject = CanonicalOrderReject(
            client_order_id="client-123",
            reason="Insufficient balance",
            timestamp="2024-01-15T10:30:45Z",
        )

        assert reject.client_order_id == "client-123"
        assert reject.reason == "Insufficient balance"
        assert reject.timestamp == "2024-01-15T10:30:45Z"

    def test_canonical_order_reject_required_fields(self) -> None:
        """Test that all fields are required."""
        with pytest.raises(ValidationError):
            CanonicalOrderReject()  # type: ignore

    def test_canonical_order_reject_serialization(self) -> None:
        """Test that CanonicalOrderReject can be serialized."""
        reject = CanonicalOrderReject(
            client_order_id="client-123",
            reason="Insufficient balance",
            timestamp="2024-01-15T10:30:45Z",
        )

        reject_dict = reject.model_dump()
        assert reject_dict["reason"] == "Insufficient balance"


class TestCanonicalFill:
    """Tests for CanonicalFill model."""

    def test_canonical_fill_creation(self) -> None:
        """Test that CanonicalFill can be created."""
        fill = CanonicalFill(
            client_order_id="client-123",
            venue_order_id="venue-456",
            fill_id="fill-789",
            size=1.0,
            price=0.55,
            fee=0.01,
            timestamp="2024-01-15T10:30:46Z",
        )

        assert fill.client_order_id == "client-123"
        assert fill.venue_order_id == "venue-456"
        assert fill.fill_id == "fill-789"
        assert fill.size == 1.0
        assert fill.price == 0.55
        assert fill.fee == 0.01

    def test_canonical_fill_optional_fields(self) -> None:
        """Test that client_order_id and venue_order_id are optional."""
        fill = CanonicalFill(
            fill_id="fill-789",
            size=1.0,
            price=0.55,
            fee=0.01,
            timestamp="2024-01-15T10:30:46Z",
        )

        assert fill.client_order_id is None
        assert fill.venue_order_id is None
        assert fill.fill_id == "fill-789"

    def test_canonical_fill_validation(self) -> None:
        """Test that CanonicalFill validates size and price."""
        # Size must be > 0
        with pytest.raises(ValidationError):
            CanonicalFill(
                fill_id="fill-789",
                size=0.0,  # Invalid: must be > 0
                price=0.55,
                fee=0.01,
                timestamp="2024-01-15T10:30:46Z",
            )

        # Price must be > 0 and <= 1
        with pytest.raises(ValidationError):
            CanonicalFill(
                fill_id="fill-789",
                size=1.0,
                price=1.5,  # Invalid: must be <= 1
                fee=0.01,
                timestamp="2024-01-15T10:30:46Z",
            )

        # Fee can be 0
        fill = CanonicalFill(
            fill_id="fill-789",
            size=1.0,
            price=0.55,
            fee=0.0,  # Valid: fee >= 0
            timestamp="2024-01-15T10:30:46Z",
        )
        assert fill.fee == 0.0

    def test_canonical_fill_serialization(self) -> None:
        """Test that CanonicalFill can be serialized."""
        fill = CanonicalFill(
            fill_id="fill-789",
            size=1.0,
            price=0.55,
            fee=0.01,
            timestamp="2024-01-15T10:30:46Z",
        )

        fill_dict = fill.model_dump()
        assert fill_dict["fill_id"] == "fill-789"
        assert fill_dict["size"] == 1.0
        assert fill_dict["price"] == 0.55


class TestCanonicalCancel:
    """Tests for CanonicalCancel model."""

    def test_canonical_cancel_creation(self) -> None:
        """Test that CanonicalCancel can be created."""
        cancel = CanonicalCancel(
            client_order_id="client-123",
            venue_order_id="venue-456",
            timestamp="2024-01-15T10:30:47Z",
        )

        assert cancel.client_order_id == "client-123"
        assert cancel.venue_order_id == "venue-456"

    def test_canonical_cancel_optional_client_order_id(self) -> None:
        """Test that client_order_id is optional."""
        cancel = CanonicalCancel(
            venue_order_id="venue-456",
            timestamp="2024-01-15T10:30:47Z",
        )

        assert cancel.client_order_id is None
        assert cancel.venue_order_id == "venue-456"

    def test_canonical_cancel_required_venue_order_id(self) -> None:
        """Test that venue_order_id is required."""
        with pytest.raises(ValidationError):
            CanonicalCancel(
                timestamp="2024-01-15T10:30:47Z"
                # Missing venue_order_id
            )  # type: ignore

    def test_canonical_cancel_serialization(self) -> None:
        """Test that CanonicalCancel can be serialized."""
        cancel = CanonicalCancel(
            venue_order_id="venue-456",
            timestamp="2024-01-15T10:30:47Z",
        )

        cancel_dict = cancel.model_dump()
        assert cancel_dict["venue_order_id"] == "venue-456"
        assert cancel_dict["client_order_id"] is None
