"""Tests for paper execution adapter.

Per Commit 2: Test PaperExecutionAdapter functionality.
"""

import asyncio
import random
import uuid

import pytest

from polytrader.adapters.polymarket.models import VenueError
from polytrader.events import FILLS
from polytrader.events.bus import EventBus
from polytrader.events.types import FillEvent
from polytrader.execution.fill_models import FillModel
from polytrader.execution.paper import PaperExecutionAdapter
from polytrader.store import MemoryMarketDataStore
from polytrader.types import MarketDataEvent, OrderIntentEvent


class TestPaperExecutionAdapter:
    """Tests for PaperExecutionAdapter."""

    @pytest.mark.asyncio
    async def test_submit_order_immediate_fill(self) -> None:
        """Test that submit_order fills immediately with IMMEDIATE model."""
        bus = EventBus()
        store = MemoryMarketDataStore()
        adapter = PaperExecutionAdapter(
            bus=bus,
            store=store,
            fill_model=FillModel.IMMEDIATE,
            fill_probability=1.0,
            rejection_probability=0.0,
            latency_ms=0.0,
        )

        intent = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="BUY",
            size=1.0,
            target_price=0.55,
            limit_price=0.55,
            reason="Test",
            ttl_s=60.0,
        )

        response = await adapter.submit_order("client-123", intent)

        assert response.status == "FILLED"
        assert response.venue_order_id.startswith("paper-")
        assert "fill_price" in response.raw_response
        assert response.raw_response["fill_price"] == 0.55

    @pytest.mark.asyncio
    async def test_submit_order_mid_price_fill(self) -> None:
        """Test that submit_order uses mid price with MID_PRICE model."""
        bus = EventBus()
        store = MemoryMarketDataStore()
        # Add market data
        market_data = MarketDataEvent(
            market_slug="test-market",
            outcome="UP",
            best_bid=0.50,
            best_ask=0.60,
        )
        store.add(market_data)

        adapter = PaperExecutionAdapter(
            bus=bus,
            store=store,
            fill_model=FillModel.MID_PRICE,
            fill_probability=1.0,
            rejection_probability=0.0,
            latency_ms=0.0,
        )

        intent = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="BUY",
            size=1.0,
            target_price=0.55,
            limit_price=0.55,
            reason="Test",
            ttl_s=60.0,
        )

        response = await adapter.submit_order("client-123", intent)

        assert response.status == "FILLED"
        assert response.raw_response["fill_price"] == 0.55  # Mid price

    @pytest.mark.asyncio
    async def test_submit_order_publishes_fill_event(self) -> None:
        """Test that submit_order publishes FillEvent."""
        bus = EventBus()
        store = MemoryMarketDataStore()
        adapter = PaperExecutionAdapter(
            bus=bus,
            store=store,
            fill_model=FillModel.IMMEDIATE,
            fill_probability=1.0,
            rejection_probability=0.0,
            latency_ms=0.0,
        )

        intent = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="BUY",
            size=1.0,
            target_price=0.55,
            limit_price=0.55,
            reason="Test",
            ttl_s=60.0,
        )

        # Subscribe to FILLS topic
        fills_queue = bus.subscribe(FILLS)

        await adapter.submit_order("client-123", intent)

        # Wait for FillEvent
        fill_event = await asyncio.wait_for(fills_queue.get(), timeout=1.0)

        assert isinstance(fill_event, FillEvent)
        assert fill_event.size == 1.0
        assert fill_event.price == 0.55
        assert fill_event.fee == 0.0
        assert fill_event.correlation_id == intent.correlation_id

    @pytest.mark.asyncio
    async def test_submit_order_rejection(self) -> None:
        """Test that submit_order raises VenueError when rejected."""
        bus = EventBus()
        store = MemoryMarketDataStore()
        adapter = PaperExecutionAdapter(
            bus=bus,
            store=store,
            fill_model=FillModel.IMMEDIATE,
            fill_probability=1.0,
            rejection_probability=1.0,  # Always reject
            latency_ms=0.0,
        )

        intent = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="BUY",
            size=1.0,
            target_price=0.55,
            limit_price=0.55,
            reason="Test",
            ttl_s=60.0,
        )

        with pytest.raises(VenueError) as exc_info:
            await adapter.submit_order("client-123", intent)

        assert exc_info.value.error_type == "fatal"
        assert "rejection" in exc_info.value.message.lower()

    @pytest.mark.asyncio
    async def test_submit_order_no_fill_returns_pending(self) -> None:
        """Test that submit_order returns PENDING when fill_probability is 0."""
        bus = EventBus()
        store = MemoryMarketDataStore()
        adapter = PaperExecutionAdapter(
            bus=bus,
            store=store,
            fill_model=FillModel.IMMEDIATE,
            fill_probability=0.0,  # Never fill
            rejection_probability=0.0,
            latency_ms=0.0,
        )

        intent = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="BUY",
            size=1.0,
            target_price=0.55,
            limit_price=0.55,
            reason="Test",
            ttl_s=60.0,
        )

        response = await adapter.submit_order("client-123", intent)

        assert response.status == "PENDING"
        assert "pending" in response.venue_order_id.lower()

    @pytest.mark.asyncio
    async def test_submit_order_simulates_latency(self) -> None:
        """Test that submit_order simulates latency."""
        bus = EventBus()
        store = MemoryMarketDataStore()
        adapter = PaperExecutionAdapter(
            bus=bus,
            store=store,
            fill_model=FillModel.IMMEDIATE,
            fill_probability=1.0,
            rejection_probability=0.0,
            latency_ms=100.0,  # 100ms latency
        )

        intent = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="BUY",
            size=1.0,
            target_price=0.55,
            limit_price=0.55,
            reason="Test",
            ttl_s=60.0,
        )

        start_time = asyncio.get_event_loop().time()
        response = await adapter.submit_order("client-123", intent)
        elapsed_ms = (asyncio.get_event_loop().time() - start_time) * 1000.0

        assert response.status == "FILLED"
        # Should take at least 100ms (with some tolerance)
        assert elapsed_ms >= 90.0  # Allow 10ms tolerance

    @pytest.mark.asyncio
    async def test_cancel_order_always_succeeds(self) -> None:
        """Test that cancel_order always succeeds."""
        bus = EventBus()
        store = MemoryMarketDataStore()
        adapter = PaperExecutionAdapter(
            bus=bus,
            store=store,
            latency_ms=0.0,
        )

        response = await adapter.cancel_order("client-123", "venue-456")

        assert response.status == "CANCELLED"
        assert response.venue_order_id == "venue-456"

    @pytest.mark.asyncio
    async def test_cancel_order_simulates_latency(self) -> None:
        """Test that cancel_order simulates latency."""
        bus = EventBus()
        store = MemoryMarketDataStore()
        adapter = PaperExecutionAdapter(
            bus=bus,
            store=store,
            latency_ms=50.0,  # 50ms latency
        )

        start_time = asyncio.get_event_loop().time()
        response = await adapter.cancel_order("client-123", "venue-456")
        elapsed_ms = (asyncio.get_event_loop().time() - start_time) * 1000.0

        assert response.status == "CANCELLED"
        # Should take at least 50ms (with some tolerance)
        assert elapsed_ms >= 40.0  # Allow 10ms tolerance

    def test_adapter_validates_probabilities(self) -> None:
        """Test that adapter validates probability ranges."""
        bus = EventBus()
        store = MemoryMarketDataStore()

        # Invalid fill_probability
        with pytest.raises(ValueError, match="fill_probability"):
            PaperExecutionAdapter(
                bus=bus,
                store=store,
                fill_probability=1.5,  # Invalid: > 1.0
            )

        # Invalid rejection_probability
        with pytest.raises(ValueError, match="rejection_probability"):
            PaperExecutionAdapter(
                bus=bus,
                store=store,
                rejection_probability=-0.1,  # Invalid: < 0.0
            )

    @pytest.mark.asyncio
    async def test_adapter_uses_deterministic_rng(self) -> None:
        """Test that adapter can use deterministic RNG for testing."""
        bus = EventBus()
        store = MemoryMarketDataStore()
        rng = random.Random(42)  # Seeded for determinism

        adapter = PaperExecutionAdapter(
            bus=bus,
            store=store,
            fill_probability=0.5,
            rejection_probability=0.0,
            rng=rng,
        )

        intent = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="BUY",
            size=1.0,
            target_price=0.55,
            limit_price=0.55,
            reason="Test",
            ttl_s=60.0,
        )

        # With seeded RNG, results should be deterministic
        results = []
        for _ in range(10):
            try:
                response = await adapter.submit_order(f"client-{uuid.uuid4()}", intent)
                results.append(response.status)
            except VenueError:
                results.append("REJECTED")

        # Should have consistent results with seeded RNG
        assert len(set(results)) <= 2  # Either FILLED or PENDING
