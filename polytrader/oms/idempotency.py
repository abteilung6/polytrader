"""OMS Idempotency: client_order_id generation and deduplication.

Per flows.mdc §7: OMS creates idempotency keys (client_order_id).
This module provides deterministic client_order_id generation and
deduplication logic to prevent duplicate order creation.
"""

import hashlib
from typing import TYPE_CHECKING

from polytrader.common.ids import get_run_id

if TYPE_CHECKING:
    from polytrader.events.types import OrderIntentEvent


def generate_client_order_id(
    intent: "OrderIntentEvent",
    run_id: str | None = None,
) -> str:
    """Generate deterministic client_order_id from intent.

    Format: {run_id}-{intent.correlation_id}-{hash(intent)}

    The client_order_id is deterministic: same intent in same run = same ID.
    This ensures idempotency: if the same intent is processed twice,
    it will generate the same client_order_id and can be deduplicated.

    Args:
        intent: Order intent event
        run_id: Optional run_id (defaults to get_run_id())

    Returns:
        Deterministic client_order_id string

    Example:
        >>> intent = OrderIntentEvent(...)
        >>> client_id = generate_client_order_id(intent)
        >>> # Same intent in same run produces same ID
        >>> assert generate_client_order_id(intent) == client_id
    """
    if run_id is None:
        run_id = get_run_id()

    # Hash the intent's key fields for determinism
    # We exclude timestamps and event_id to ensure same intent = same hash
    intent_hash = _hash_intent(intent)

    # Format: {run_id}-{correlation_id}-{hash}
    return f"{run_id}-{intent.correlation_id}-{intent_hash}"


def _hash_intent(intent: "OrderIntentEvent") -> str:
    """Generate deterministic hash from intent key fields.

    Hashes the fields that define the order intent:
    - market_slug
    - outcome
    - side
    - target_price
    - limit_price
    - size

    Excludes:
    - timestamps (ts_wall, ts_mono)
    - event_id (unique per event instance)
    - reason (may vary for same intent)
    - ttl_s (may vary)

    Args:
        intent: Order intent event

    Returns:
        Hex digest of the hash (first 16 characters for brevity)
    """
    # Create a deterministic string representation
    intent_str = (
        f"{intent.market_slug}:{intent.outcome}:{intent.side}:"
        f"{intent.target_price}:{intent.limit_price}:{intent.size}"
    )

    # Hash using SHA256 and take first 16 chars for brevity
    hash_obj = hashlib.sha256(intent_str.encode("utf-8"))
    return hash_obj.hexdigest()[:16]


class IdempotencyStore:
    """Tracks client_order_id → order_id mapping for deduplication.

    Per flows.mdc §7: OMS must handle duplicate submits idempotently.
    This store maintains the mapping between client_order_id (idempotency key)
    and order_id (internal UUID) to detect and handle duplicate order creation.

    Attributes:
        _mappings: Dictionary mapping client_order_id → order_id
    """

    def __init__(self) -> None:
        """Initialize empty idempotency store."""
        self._mappings: dict[str, str] = {}

    def record_order(self, client_order_id: str, order_id: str) -> None:
        """Record mapping between client_order_id and order_id.

        Args:
            client_order_id: Idempotency key
            order_id: Internal order UUID

        Raises:
            ValueError: If client_order_id already exists with different order_id
        """
        if client_order_id in self._mappings:
            existing_order_id = self._mappings[client_order_id]
            if existing_order_id != order_id:
                raise ValueError(
                    f"client_order_id {client_order_id} already mapped to "
                    f"order_id {existing_order_id}, cannot map to {order_id}"
                )
        else:
            self._mappings[client_order_id] = order_id

    def get_order_id(self, client_order_id: str) -> str | None:
        """Get order_id if client_order_id already exists.

        Args:
            client_order_id: Idempotency key to look up

        Returns:
            Existing order_id if found, None otherwise
        """
        return self._mappings.get(client_order_id)

    def is_duplicate(self, client_order_id: str) -> bool:
        """Check if client_order_id already processed.

        Args:
            client_order_id: Idempotency key to check

        Returns:
            True if client_order_id exists, False otherwise
        """
        return client_order_id in self._mappings

    def clear(self) -> None:
        """Clear all mappings (for testing/reset)."""
        self._mappings.clear()

    def get_all_mappings(self) -> dict[str, str]:
        """Get all mappings (for debugging/testing).

        Returns:
            Copy of the mappings dictionary
        """
        return self._mappings.copy()
