"""Tests for OMS idempotency: client_order_id generation and deduplication.

Per flows.mdc §7: OMS must handle duplicate submits idempotently.
"""

import pytest

from polytrader.common.ids import get_run_id, reset_run_id
from polytrader.events.types import OrderIntentEvent
from polytrader.oms.idempotency import IdempotencyStore, generate_client_order_id


def create_test_intent(
    market_slug: str = "test-market",
    outcome: str = "UP",
    side: str = "BUY",
    target_price: float = 0.5,
    limit_price: float = 0.45,
    size: float = 1.0,
    reason: str = "Test intent",
    strategy_id: str = "simple_threshold",
) -> OrderIntentEvent:
    """Create a test OrderIntentEvent."""
    return OrderIntentEvent(
        market_slug=market_slug,
        outcome=outcome,
        side=side,
        target_price=target_price,
        limit_price=limit_price,
        size=size,
        reason=reason,
        strategy_id=strategy_id,
    )


class TestGenerateClientOrderId:
    """Tests for generate_client_order_id function."""

    def test_generate_client_order_id_deterministic(self) -> None:
        """Test that same intent produces same client_order_id."""
        intent = create_test_intent()

        client_id1 = generate_client_order_id(intent)
        client_id2 = generate_client_order_id(intent)

        assert client_id1 == client_id2

    def test_generate_client_order_id_format(self) -> None:
        """Test that client_order_id has expected format."""
        intent = create_test_intent()
        run_id = get_run_id()

        client_id = generate_client_order_id(intent, run_id=run_id)

        # Format: {run_id}-{correlation_id}-{hash}
        # Note: run_id and correlation_id are UUIDs with dashes, so we can't simply split
        # Instead, verify the structure: starts with run_id, contains correlation_id, ends with hash
        assert client_id.startswith(run_id)
        assert intent.correlation_id in client_id
        # Hash is last 16 characters (after final dash)
        hash_part = client_id.split("-")[-1]
        assert len(hash_part) == 16  # Hash is 16 hex chars
        assert all(c in "0123456789abcdef" for c in hash_part)  # Hex characters

    def test_generate_client_order_id_different_intents(self) -> None:
        """Test that different intents produce different client_order_ids."""
        intent1 = create_test_intent(size=1.0)
        intent2 = create_test_intent(size=2.0)

        client_id1 = generate_client_order_id(intent1)
        client_id2 = generate_client_order_id(intent2)

        assert client_id1 != client_id2

    def test_generate_client_order_id_same_fields_same_id(self) -> None:
        """Test that intents with same key fields produce same ID."""
        # Create first intent
        intent1 = create_test_intent(
            market_slug="test-market",
            outcome="UP",
            side="BUY",
            target_price=0.5,
            limit_price=0.45,
            size=1.0,
            reason="Reason 1",
        )

        # Create second intent with same key fields but different reason
        # Use model_copy to set same correlation_id (since Event is frozen)
        intent2 = intent1.model_copy(update={"reason": "Reason 2"})

        # Use same run_id
        run_id = get_run_id()

        client_id1 = generate_client_order_id(intent1, run_id=run_id)
        client_id2 = generate_client_order_id(intent2, run_id=run_id)

        # Should be same because key fields (market, outcome, side, prices, size) are same
        # and correlation_id is same (from model_copy)
        assert client_id1 == client_id2

    def test_generate_client_order_id_different_correlation_ids(self) -> None:
        """Test that different correlation_ids produce different client_order_ids."""
        intent1 = create_test_intent()
        intent2 = create_test_intent()

        # Ensure correlation_ids are different
        assert intent1.correlation_id != intent2.correlation_id

        run_id = get_run_id()
        client_id1 = generate_client_order_id(intent1, run_id=run_id)
        client_id2 = generate_client_order_id(intent2, run_id=run_id)

        assert client_id1 != client_id2

    def test_generate_client_order_id_different_strategy_ids(self) -> None:
        """Different strategy instances (same market/side/size) get different client_order_ids."""
        intent1 = create_test_intent(strategy_id="vfmr-instance-1")
        intent2 = create_test_intent(strategy_id="vfmr-instance-2")
        run_id = get_run_id()

        client_id1 = generate_client_order_id(intent1, run_id=run_id)
        client_id2 = generate_client_order_id(intent2, run_id=run_id)

        assert client_id1 != client_id2

    def test_generate_client_order_id_different_run_ids(self) -> None:
        """Test that different run_ids produce different client_order_ids."""
        intent = create_test_intent()

        client_id1 = generate_client_order_id(intent, run_id="run-1")
        client_id2 = generate_client_order_id(intent, run_id="run-2")

        assert client_id1 != client_id2

    def test_generate_client_order_id_uses_get_run_id_by_default(self) -> None:
        """Test that generate_client_order_id uses get_run_id() by default."""
        reset_run_id()
        intent = create_test_intent()

        client_id = generate_client_order_id(intent)

        # Should include the run_id from get_run_id()
        run_id = get_run_id()
        assert client_id.startswith(run_id)


class TestIdempotencyStore:
    """Tests for IdempotencyStore class."""

    def test_record_order(self) -> None:
        """Test recording a new order mapping."""
        store = IdempotencyStore()

        store.record_order("client-123", "order-456")

        assert store.get_order_id("client-123") == "order-456"
        assert store.is_duplicate("client-123") is True

    def test_record_order_idempotent(self) -> None:
        """Test that recording same mapping twice is idempotent."""
        store = IdempotencyStore()

        store.record_order("client-123", "order-456")
        # Record again with same mapping
        store.record_order("client-123", "order-456")

        assert store.get_order_id("client-123") == "order-456"

    def test_record_order_conflict_raises(self) -> None:
        """Test that recording different order_id for same client_order_id raises."""
        store = IdempotencyStore()

        store.record_order("client-123", "order-456")

        with pytest.raises(ValueError, match="already mapped"):
            store.record_order("client-123", "order-789")

    def test_get_order_id_existing(self) -> None:
        """Test getting order_id for existing client_order_id."""
        store = IdempotencyStore()

        store.record_order("client-123", "order-456")

        assert store.get_order_id("client-123") == "order-456"

    def test_get_order_id_nonexistent(self) -> None:
        """Test getting order_id for non-existent client_order_id."""
        store = IdempotencyStore()

        assert store.get_order_id("client-123") is None

    def test_is_duplicate_existing(self) -> None:
        """Test checking duplicate for existing client_order_id."""
        store = IdempotencyStore()

        store.record_order("client-123", "order-456")

        assert store.is_duplicate("client-123") is True

    def test_is_duplicate_nonexistent(self) -> None:
        """Test checking duplicate for non-existent client_order_id."""
        store = IdempotencyStore()

        assert store.is_duplicate("client-123") is False

    def test_clear(self) -> None:
        """Test clearing all mappings."""
        store = IdempotencyStore()

        store.record_order("client-123", "order-456")
        store.record_order("client-789", "order-012")

        assert len(store.get_all_mappings()) == 2

        store.clear()

        assert len(store.get_all_mappings()) == 0
        assert store.get_order_id("client-123") is None
        assert store.is_duplicate("client-123") is False

    def test_get_all_mappings(self) -> None:
        """Test getting all mappings."""
        store = IdempotencyStore()

        store.record_order("client-123", "order-456")
        store.record_order("client-789", "order-012")

        mappings = store.get_all_mappings()

        assert mappings == {"client-123": "order-456", "client-789": "order-012"}
        # Should be a copy, not the original
        assert mappings is not store._mappings

    def test_multiple_orders(self) -> None:
        """Test storing multiple order mappings."""
        store = IdempotencyStore()

        store.record_order("client-1", "order-1")
        store.record_order("client-2", "order-2")
        store.record_order("client-3", "order-3")

        assert store.get_order_id("client-1") == "order-1"
        assert store.get_order_id("client-2") == "order-2"
        assert store.get_order_id("client-3") == "order-3"

        assert store.is_duplicate("client-1") is True
        assert store.is_duplicate("client-2") is True
        assert store.is_duplicate("client-3") is True
        assert store.is_duplicate("client-4") is False


class TestIdempotencyIntegration:
    """Integration tests for idempotency workflow."""

    def test_deduplication_workflow(self) -> None:
        """Test complete deduplication workflow."""
        store = IdempotencyStore()
        intent = create_test_intent()

        # First time: generate client_order_id and record
        client_order_id = generate_client_order_id(intent)
        order_id1 = "order-123"

        # Check if duplicate
        assert store.is_duplicate(client_order_id) is False

        # Record the order
        store.record_order(client_order_id, order_id1)

        # Second time: same intent should produce same client_order_id
        client_order_id2 = generate_client_order_id(intent)
        assert client_order_id == client_order_id2

        # Check if duplicate
        assert store.is_duplicate(client_order_id2) is True

        # Get existing order_id
        existing_order_id = store.get_order_id(client_order_id2)
        assert existing_order_id == order_id1

    def test_restart_scenario(self) -> None:
        """Test idempotency behavior after restart (new run_id)."""
        # Simulate first run
        reset_run_id()
        intent = create_test_intent()
        run_id1 = get_run_id()

        client_id1 = generate_client_order_id(intent, run_id=run_id1)

        # Simulate restart: new run_id
        reset_run_id()
        run_id2 = get_run_id()
        assert run_id1 != run_id2

        # Same intent in new run produces different client_order_id
        client_id2 = generate_client_order_id(intent, run_id=run_id2)

        assert client_id1 != client_id2

        # This is expected: after restart, same intent creates new order
        # (idempotency is per-run, not across runs)

    def test_different_intents_same_run(self) -> None:
        """Test that different intents in same run produce different IDs."""
        intent1 = create_test_intent(size=1.0)
        intent2 = create_test_intent(size=2.0)

        run_id = get_run_id()
        client_id1 = generate_client_order_id(intent1, run_id=run_id)
        client_id2 = generate_client_order_id(intent2, run_id=run_id)

        assert client_id1 != client_id2

        # Both should be unique
        store = IdempotencyStore()
        store.record_order(client_id1, "order-1")
        store.record_order(client_id2, "order-2")

        assert store.get_order_id(client_id1) == "order-1"
        assert store.get_order_id(client_id2) == "order-2"
