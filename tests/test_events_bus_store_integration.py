"""Tests for EventBus and EventStore integration."""

from polytrader.events import EventBus, MemoryEventStore
from polytrader.events.topics import MARKET_DATA, ORDERS, PROPOSALS
from polytrader.types import (
    MarketDataEvent,
    OrderExecutedEvent,
    OrderIntentEvent,
)


class TestEventBusStoreIntegration:
    """Tests for EventBus automatic event persistence."""

    async def test_eventbus_auto_persists_events(self) -> None:
        """Test that EventBus automatically persists Event instances."""
        store = MemoryEventStore()
        bus = EventBus(store=store)

        # Publish a MarketDataEvent
        event = MarketDataEvent(
            market_slug="test-market",
            outcome="UP",
            best_bid=0.45,
            best_ask=0.55,
        )
        await bus.publish(MARKET_DATA, event)

        # Verify event was persisted
        events = list(store.read_stream(event_type=MarketDataEvent))
        assert len(events) == 1
        persisted_event = events[0]
        assert isinstance(persisted_event, MarketDataEvent)
        assert persisted_event.event_id == event.event_id
        assert persisted_event.market_slug == "test-market"

    async def test_eventbus_persists_all_event_types(self) -> None:
        """Test that EventBus persists all event types."""
        store = MemoryEventStore()
        bus = EventBus(store=store)

        # Publish different event types
        market_event = MarketDataEvent(
            market_slug="test-market",
            outcome="UP",
            best_bid=0.45,
            best_ask=0.55,
        )
        intent_event = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="BUY",
            target_price=0.6,
            limit_price=0.55,
            size=1.0,
            reason="Test",
        )
        executed_event = OrderExecutedEvent(
            market_slug="test-market",
            outcome="UP",
            side="BUY",
            size=1.0,
            target_price=0.6,
            proposal_reason="Test",
            response={"order_id": "123"},
        )

        await bus.publish(MARKET_DATA, market_event)
        await bus.publish(PROPOSALS, intent_event)
        await bus.publish(ORDERS, executed_event)

        # Verify all events were persisted
        assert store.count() == 3
        assert len(list(store.read_stream(event_type=MarketDataEvent))) == 1
        assert len(list(store.read_stream(event_type=OrderIntentEvent))) == 1
        assert len(list(store.read_stream(event_type=OrderExecutedEvent))) == 1

    async def test_eventbus_ignores_non_event_messages(self) -> None:
        """Test that EventBus ignores non-Event messages."""
        store = MemoryEventStore()
        bus = EventBus(store=store)

        # Create a topic for non-Event messages
        from polytrader.events.bus import Topic

        non_event_topic = Topic[str]("test_topic")

        # Publish a non-Event message
        await bus.publish(non_event_topic, "not an event")

        # Verify nothing was persisted
        assert store.count() == 0

    async def test_eventbus_works_without_store(self) -> None:
        """Test that EventBus works without a store (backward compatibility)."""
        bus = EventBus()  # No store

        # Publish an event
        event = MarketDataEvent(
            market_slug="test-market",
            outcome="UP",
            best_bid=0.45,
            best_ask=0.55,
        )
        # Should not raise an error
        await bus.publish(MARKET_DATA, event)

    async def test_eventbus_idempotency(self) -> None:
        """Test that EventBus idempotency works (duplicate events not stored twice)."""
        store = MemoryEventStore()
        bus = EventBus(store=store)

        # Create an event
        event = MarketDataEvent(
            market_slug="test-market",
            outcome="UP",
            best_bid=0.45,
            best_ask=0.55,
        )

        # Publish the same event twice
        await bus.publish(MARKET_DATA, event)
        await bus.publish(MARKET_DATA, event)

        # Verify event was only stored once (idempotency)
        assert store.count() == 1
        events = list(store.read_stream(event_type=MarketDataEvent))
        assert len(events) == 1
        assert events[0].event_id == event.event_id

    async def test_eventbus_persists_before_publishing(self) -> None:
        """Test that EventBus persists events before publishing to subscribers."""
        store = MemoryEventStore()
        bus = EventBus(store=store)

        # Subscribe to topic
        queue = bus.subscribe(MARKET_DATA)

        # Publish event
        event = MarketDataEvent(
            market_slug="test-market",
            outcome="UP",
            best_bid=0.45,
            best_ask=0.55,
        )
        await bus.publish(MARKET_DATA, event)

        # Verify event was persisted before subscriber received it
        # (We can't guarantee exact timing, but we can verify both happened)
        assert store.count() == 1
        received = await queue.get()
        assert received.event_id == event.event_id

    async def test_eventbus_continues_on_persistence_error(self) -> None:
        """Test that EventBus continues publishing even if persistence fails."""

        # Create a store that raises an error
        class FailingEventStore(MemoryEventStore):
            async def append(self, event) -> None:
                raise RuntimeError("Persistence failed")

        store = FailingEventStore()
        bus = EventBus(store=store)

        # Subscribe to topic
        queue = bus.subscribe(MARKET_DATA)

        # Publish event (should not raise, even though persistence fails)
        event = MarketDataEvent(
            market_slug="test-market",
            outcome="UP",
            best_bid=0.45,
            best_ask=0.55,
        )
        # Should not raise an error
        await bus.publish(MARKET_DATA, event)

        # Verify event was still delivered to subscriber
        received = await queue.get()
        assert received.event_id == event.event_id

        # Verify event was NOT persisted (due to error)
        assert store.count() == 0
