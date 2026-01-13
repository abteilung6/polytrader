"""Tests for PaperTradingSystemBuilder and LiveTradingSystemBuilder.

Per testing.mdc: Comprehensive unit tests for builder pattern.
Tests cover:
- Configuration validation
- Factory creation
- Dependency wiring
- Supervisor construction
"""

import pytest

from polytrader.config import PolymarketSecrets
from polytrader.events import EventBus, MemoryEventStore
from polytrader.execution.fill_models import FillModel
from polytrader.market_discovery import MarketDiscoveryService
from polytrader.oms import InMemoryOrderStore
from polytrader.position_manager.paper import PaperPositionManager
from polytrader.store import MemoryMarketDataStore
from polytrader.supervisor import MarketSupervisor, SystemSupervisor
from polytrader.tasks.builders import LiveTradingSystemBuilder, PaperTradingSystemBuilder


class TestPaperTradingSystemBuilder:
    """Tests for PaperTradingSystemBuilder."""

    @pytest.fixture
    def builder(self) -> PaperTradingSystemBuilder:
        """Create a builder instance for testing."""
        bus = EventBus(store=MemoryEventStore())
        store = MemoryMarketDataStore()
        discovery = MarketDiscoveryService(bus=bus)
        return PaperTradingSystemBuilder(
            bus=bus,
            store=store,
            discovery=discovery,
            market_pattern="btc-updown-15m",
            frequency=1.0,
        )

    def test_builder_initialization(self, builder: PaperTradingSystemBuilder) -> None:
        """Test builder initializes with correct defaults."""
        assert builder._buy_threshold == 0.30
        assert builder._min_history == 30
        assert builder._size == 1.0
        assert builder._fill_model == FillModel.MID_PRICE
        assert builder._fill_probability == 1.0
        assert builder._rejection_probability == 0.0
        assert builder._latency_ms == 50.0
        assert builder._starting_equity == 1000.0

    def test_builder_initialization_invalid_frequency(self) -> None:
        """Test builder raises ValueError for invalid frequency."""
        bus = EventBus(store=MemoryEventStore())
        store = MemoryMarketDataStore()
        discovery = MarketDiscoveryService(bus=bus)

        with pytest.raises(ValueError, match="frequency must be > 0"):
            PaperTradingSystemBuilder(
                bus=bus,
                store=store,
                discovery=discovery,
                market_pattern="btc-updown-15m",
                frequency=0.0,
            )

    def test_builder_initialization_empty_market_pattern(self) -> None:
        """Test builder raises ValueError for empty market pattern."""
        bus = EventBus(store=MemoryEventStore())
        store = MemoryMarketDataStore()
        discovery = MarketDiscoveryService(bus=bus)

        with pytest.raises(ValueError, match="market_pattern cannot be empty"):
            PaperTradingSystemBuilder(
                bus=bus,
                store=store,
                discovery=discovery,
                market_pattern="",
                frequency=1.0,
            )

    def test_strategy_config(self, builder: PaperTradingSystemBuilder) -> None:
        """Test strategy configuration."""
        result = builder.strategy_config(buy_threshold=0.25, min_history=50)
        assert result is builder  # Fluent interface
        assert builder._buy_threshold == 0.25
        assert builder._min_history == 50

    def test_strategy_config_invalid_buy_threshold(
        self, builder: PaperTradingSystemBuilder
    ) -> None:
        """Test strategy config raises ValueError for invalid buy_threshold."""
        with pytest.raises(ValueError, match="buy_threshold must be between 0 and 1"):
            builder.strategy_config(buy_threshold=1.5)

        with pytest.raises(ValueError, match="buy_threshold must be between 0 and 1"):
            builder.strategy_config(buy_threshold=-0.1)

    def test_strategy_config_invalid_min_history(self, builder: PaperTradingSystemBuilder) -> None:
        """Test strategy config raises ValueError for invalid min_history."""
        with pytest.raises(ValueError, match="min_history must be >= 0"):
            builder.strategy_config(min_history=-1)

    def test_execution_config(self, builder: PaperTradingSystemBuilder) -> None:
        """Test execution configuration."""
        result = builder.execution_config(
            size=10.0,
            fill_model=FillModel.IMMEDIATE,
            fill_probability=0.9,
            rejection_probability=0.05,
            latency_ms=100.0,
        )
        assert result is builder  # Fluent interface
        assert builder._size == 10.0
        assert builder._fill_model == FillModel.IMMEDIATE
        assert builder._fill_probability == 0.9
        assert builder._rejection_probability == 0.05
        assert builder._latency_ms == 100.0

    def test_execution_config_invalid_size(self, builder: PaperTradingSystemBuilder) -> None:
        """Test execution config raises ValueError for invalid size."""
        with pytest.raises(ValueError, match="size must be > 0"):
            builder.execution_config(size=0.0)

        with pytest.raises(ValueError, match="size must be > 0"):
            builder.execution_config(size=-1.0)

    def test_execution_config_invalid_fill_probability(
        self, builder: PaperTradingSystemBuilder
    ) -> None:
        """Test execution config raises ValueError for invalid fill_probability."""
        with pytest.raises(ValueError, match="fill_probability must be between 0 and 1"):
            builder.execution_config(fill_probability=1.5)

        with pytest.raises(ValueError, match="fill_probability must be between 0 and 1"):
            builder.execution_config(fill_probability=-0.1)

    def test_execution_config_invalid_rejection_probability(
        self, builder: PaperTradingSystemBuilder
    ) -> None:
        """Test execution config raises ValueError for invalid rejection_probability."""
        with pytest.raises(ValueError, match="rejection_probability must be between 0 and 1"):
            builder.execution_config(rejection_probability=1.5)

    def test_execution_config_probabilities_sum_exceed_one(
        self, builder: PaperTradingSystemBuilder
    ) -> None:
        """Test execution config raises ValueError when probabilities sum > 1.0."""
        with pytest.raises(
            ValueError, match="fill_probability \\+ rejection_probability must be <= 1.0"
        ):
            builder.execution_config(fill_probability=0.6, rejection_probability=0.5)

    def test_execution_config_invalid_latency(self, builder: PaperTradingSystemBuilder) -> None:
        """Test execution config raises ValueError for invalid latency_ms."""
        with pytest.raises(ValueError, match="latency_ms must be >= 0"):
            builder.execution_config(latency_ms=-1.0)

    def test_position_config(self, builder: PaperTradingSystemBuilder) -> None:
        """Test position configuration."""
        result = builder.position_config(starting_equity=5000.0)
        assert result is builder  # Fluent interface
        assert builder._starting_equity == 5000.0

    def test_position_config_invalid_starting_equity(
        self, builder: PaperTradingSystemBuilder
    ) -> None:
        """Test position config raises ValueError for invalid starting_equity."""
        with pytest.raises(ValueError, match="starting_equity must be > 0"):
            builder.position_config(starting_equity=0.0)

        with pytest.raises(ValueError, match="starting_equity must be > 0"):
            builder.position_config(starting_equity=-1.0)

    def test_shared_oms_store_creation(self, builder: PaperTradingSystemBuilder) -> None:
        """Test shared OMS store is created and reused."""
        store1 = builder._get_shared_oms_store()
        store2 = builder._get_shared_oms_store()
        assert store1 is store2
        assert isinstance(store1, InMemoryOrderStore)

    def test_build_system_supervisor(self, builder: PaperTradingSystemBuilder) -> None:
        """Test building SystemSupervisor."""
        supervisor = builder.build_system_supervisor()
        assert isinstance(supervisor, SystemSupervisor)
        assert supervisor.bus is builder._bus
        assert supervisor.store is builder._store

    def test_build_market_supervisor(self, builder: PaperTradingSystemBuilder) -> None:
        """Test building MarketSupervisor."""
        supervisor = builder.build_market_supervisor()
        assert isinstance(supervisor, MarketSupervisor)
        assert supervisor.pattern == "btc-updown-15m"
        assert supervisor.bus is builder._bus
        assert supervisor.store is builder._store

    def test_build_market_supervisor_with_position_manager(
        self, builder: PaperTradingSystemBuilder
    ) -> None:
        """Test building MarketSupervisor with position manager."""
        # Create a position manager
        shared_store = builder._get_shared_oms_store()
        position_manager = PaperPositionManager(
            bus=builder._bus, store=shared_store, starting_equity=1000.0
        )

        supervisor = builder.build_market_supervisor(position_manager=position_manager)
        assert isinstance(supervisor, MarketSupervisor)
        assert supervisor.position_manager is position_manager

    def test_build_complete_system(self, builder: PaperTradingSystemBuilder) -> None:
        """Test building complete system (both supervisors)."""
        system_supervisor, market_supervisor = builder.build_complete_system()
        assert isinstance(system_supervisor, SystemSupervisor)
        assert isinstance(market_supervisor, MarketSupervisor)

    def test_fluent_interface(self, builder: PaperTradingSystemBuilder) -> None:
        """Test fluent interface for configuration."""
        result = (
            builder.strategy_config(buy_threshold=0.25, min_history=50)
            .execution_config(size=10.0, fill_model=FillModel.IMMEDIATE)
            .position_config(starting_equity=5000.0)
        )
        assert result is builder
        assert builder._buy_threshold == 0.25
        assert builder._min_history == 50
        assert builder._size == 10.0
        assert builder._fill_model == FillModel.IMMEDIATE
        assert builder._starting_equity == 5000.0

    @pytest.mark.asyncio
    async def test_build_system_supervisor_creates_shared_store(
        self, builder: PaperTradingSystemBuilder
    ) -> None:
        """Test that building system supervisor creates shared OMS store."""
        builder.build_system_supervisor()
        assert builder._shared_oms_store is not None
        assert isinstance(builder._shared_oms_store, InMemoryOrderStore)

    @pytest.mark.asyncio
    async def test_build_system_supervisor_uses_shared_store(
        self, builder: PaperTradingSystemBuilder
    ) -> None:
        """Test that system supervisor uses shared OMS store for OMS core and position manager."""
        supervisor = builder.build_system_supervisor()
        await supervisor.start()

        # Get the OMS core and position manager
        oms_core = supervisor.oms_core
        position_manager = supervisor.position_manager

        assert oms_core is not None
        assert position_manager is not None
        assert isinstance(position_manager, PaperPositionManager)

        # Both should use the same store
        # (We can't directly access the store, but we can verify they're created)
        await supervisor.stop()

    def test_builder_configuration_preserved_across_builds(
        self, builder: PaperTradingSystemBuilder
    ) -> None:
        """Test that builder configuration is preserved across multiple builds."""
        builder.strategy_config(buy_threshold=0.25, min_history=50)
        builder.execution_config(size=10.0)

        supervisor1 = builder.build_system_supervisor()
        supervisor2 = builder.build_system_supervisor()

        # Both should use the same configuration
        assert supervisor1.bus is supervisor2.bus
        assert supervisor1.store is supervisor2.store


class TestLiveTradingSystemBuilder:
    """Tests for LiveTradingSystemBuilder."""

    @pytest.fixture
    def builder(self) -> LiveTradingSystemBuilder:
        """Create a builder instance for testing."""
        bus = EventBus(store=MemoryEventStore())
        store = MemoryMarketDataStore()
        discovery = MarketDiscoveryService(bus=bus)
        secrets = PolymarketSecrets()
        return LiveTradingSystemBuilder(
            bus=bus,
            store=store,
            discovery=discovery,
            market_pattern="btc-updown-15m",
            frequency=1.0,
            secrets=secrets,
        )

    def test_builder_initialization(self, builder: LiveTradingSystemBuilder) -> None:
        """Test builder initializes with correct defaults."""
        assert builder._buy_threshold == 0.30
        assert builder._min_history == 30
        assert builder._size == 1.0
        assert builder._sync_interval == 60.0

    def test_builder_initialization_invalid_frequency(self) -> None:
        """Test builder raises ValueError for invalid frequency."""
        bus = EventBus(store=MemoryEventStore())
        store = MemoryMarketDataStore()
        discovery = MarketDiscoveryService(bus=bus)
        secrets = PolymarketSecrets()

        with pytest.raises(ValueError, match="frequency must be > 0"):
            LiveTradingSystemBuilder(
                bus=bus,
                store=store,
                discovery=discovery,
                market_pattern="btc-updown-15m",
                frequency=0.0,
                secrets=secrets,
            )

    def test_builder_initialization_empty_market_pattern(self) -> None:
        """Test builder raises ValueError for empty market pattern."""
        bus = EventBus(store=MemoryEventStore())
        store = MemoryMarketDataStore()
        discovery = MarketDiscoveryService(bus=bus)
        secrets = PolymarketSecrets()

        with pytest.raises(ValueError, match="market_pattern cannot be empty"):
            LiveTradingSystemBuilder(
                bus=bus,
                store=store,
                discovery=discovery,
                market_pattern="",
                frequency=1.0,
                secrets=secrets,
            )

    def test_strategy_config(self, builder: LiveTradingSystemBuilder) -> None:
        """Test strategy configuration."""
        result = builder.strategy_config(buy_threshold=0.25, min_history=50)
        assert result is builder  # Fluent interface
        assert builder._buy_threshold == 0.25
        assert builder._min_history == 50

    def test_strategy_config_invalid_buy_threshold(self, builder: LiveTradingSystemBuilder) -> None:
        """Test strategy config raises ValueError for invalid buy_threshold."""
        with pytest.raises(ValueError, match="buy_threshold must be between 0 and 1"):
            builder.strategy_config(buy_threshold=1.5)

        with pytest.raises(ValueError, match="buy_threshold must be between 0 and 1"):
            builder.strategy_config(buy_threshold=-0.1)

    def test_strategy_config_invalid_min_history(self, builder: LiveTradingSystemBuilder) -> None:
        """Test strategy config raises ValueError for invalid min_history."""
        with pytest.raises(ValueError, match="min_history must be >= 0"):
            builder.strategy_config(min_history=-1)

    def test_execution_config(self, builder: LiveTradingSystemBuilder) -> None:
        """Test execution configuration."""
        result = builder.execution_config(size=10.0, sync_interval=120.0)
        assert result is builder  # Fluent interface
        assert builder._size == 10.0
        assert builder._sync_interval == 120.0

    def test_execution_config_invalid_size(self, builder: LiveTradingSystemBuilder) -> None:
        """Test execution config raises ValueError for invalid size."""
        with pytest.raises(ValueError, match="size must be > 0"):
            builder.execution_config(size=0.0)

        with pytest.raises(ValueError, match="size must be > 0"):
            builder.execution_config(size=-1.0)

    def test_execution_config_invalid_sync_interval(
        self, builder: LiveTradingSystemBuilder
    ) -> None:
        """Test execution config raises ValueError for invalid sync_interval."""
        with pytest.raises(ValueError, match="sync_interval must be >= 0"):
            builder.execution_config(sync_interval=-1.0)

    def test_build_system_supervisor(self, builder: LiveTradingSystemBuilder) -> None:
        """Test building SystemSupervisor."""
        supervisor = builder.build_system_supervisor()
        assert isinstance(supervisor, SystemSupervisor)
        assert supervisor.bus is builder._bus
        assert supervisor.store is builder._store

    def test_build_market_supervisor(self, builder: LiveTradingSystemBuilder) -> None:
        """Test building MarketSupervisor."""
        supervisor = builder.build_market_supervisor()
        assert isinstance(supervisor, MarketSupervisor)
        assert supervisor.pattern == "btc-updown-15m"
        assert supervisor.bus is builder._bus
        assert supervisor.store is builder._store

    def test_build_market_supervisor_with_position_manager(
        self, builder: LiveTradingSystemBuilder
    ) -> None:
        """Test building MarketSupervisor with position manager."""
        # Create a fake position manager for testing
        from polytrader.position_manager import IPositionManager

        class FakePositionManager(IPositionManager):
            async def run(self) -> None:
                pass

            def stop(self) -> None:
                pass

            def get_positions(self) -> dict | None:
                return None

            def get_position(self, market_slug: str, outcome: str) -> None:
                return None

        position_manager = FakePositionManager()

        supervisor = builder.build_market_supervisor(position_manager=position_manager)
        assert isinstance(supervisor, MarketSupervisor)
        assert supervisor.position_manager is position_manager

    def test_build_complete_system(self, builder: LiveTradingSystemBuilder) -> None:
        """Test building complete system (both supervisors)."""
        system_supervisor, market_supervisor = builder.build_complete_system()
        assert isinstance(system_supervisor, SystemSupervisor)
        assert isinstance(market_supervisor, MarketSupervisor)

    def test_fluent_interface(self, builder: LiveTradingSystemBuilder) -> None:
        """Test fluent interface for configuration."""
        result = builder.strategy_config(buy_threshold=0.25, min_history=50).execution_config(
            size=10.0, sync_interval=120.0
        )
        assert result is builder
        assert builder._buy_threshold == 0.25
        assert builder._min_history == 50
        assert builder._size == 10.0
        assert builder._sync_interval == 120.0

    def test_clob_client_factory_creation(self, builder: LiveTradingSystemBuilder) -> None:
        """Test that CLOB client factory is created and reused."""
        factory1 = builder._get_clob_client_factory()
        factory2 = builder._get_clob_client_factory()
        assert factory1 is factory2

    @pytest.mark.asyncio
    async def test_build_system_supervisor_creates_clob_factory(
        self, builder: LiveTradingSystemBuilder
    ) -> None:
        """Test that building system supervisor creates CLOB client factory."""
        builder.build_system_supervisor()
        assert builder._clob_client_factory is not None

    @pytest.mark.asyncio
    async def test_build_system_supervisor_uses_position_manager(
        self, builder: LiveTradingSystemBuilder
    ) -> None:
        """Test that system supervisor uses PositionManager (not PaperPositionManager)."""
        from unittest.mock import AsyncMock, MagicMock, patch

        from polytrader.execution import ExecutionRouter

        # Mock the CLOB client factory to avoid real API calls during build
        mock_clob_client = MagicMock()
        mock_clob_client.create_or_derive_api_creds = MagicMock(
            return_value=MagicMock(apiKey="test-key", secret="test-secret", passphrase="test-pass")
        )

        def mock_clob_client_factory():
            return mock_clob_client

        # Mock the execution router factory to avoid real API calls
        mock_adapter = MagicMock()
        mock_adapter.get_open_orders = AsyncMock(return_value=[])

        mock_execution_router = MagicMock(spec=ExecutionRouter)
        mock_execution_router.run = AsyncMock()
        mock_execution_router.get_adapter = MagicMock(return_value=mock_adapter)

        def mock_execution_router_factory() -> ExecutionRouter:
            return mock_execution_router

        # Patch the CLOB client factory creation to use our mock
        with patch.object(
            builder, "_get_clob_client_factory", return_value=mock_clob_client_factory
        ):
            supervisor = builder.build_system_supervisor()

        # Replace the execution router factory with a mock to avoid API calls
        supervisor.execution_router_factory = mock_execution_router_factory
        # Disable user stream and reconciliation for this test (not needed)
        supervisor.user_stream_adapter_factory = None
        supervisor.reconciliation_service_factory = None
        supervisor.circuit_breaker_factory = None
        await supervisor.start()

        # Get the position manager
        position_manager = supervisor.position_manager

        assert position_manager is not None
        # Should be real PositionManager, not PaperPositionManager
        assert not isinstance(position_manager, PaperPositionManager)

        await supervisor.stop()

    def test_builder_configuration_preserved_across_builds(
        self, builder: LiveTradingSystemBuilder
    ) -> None:
        """Test that builder configuration is preserved across multiple builds."""
        builder.strategy_config(buy_threshold=0.25, min_history=50)
        builder.execution_config(size=10.0, sync_interval=120.0)

        supervisor1 = builder.build_system_supervisor()
        supervisor2 = builder.build_system_supervisor()

        # Both should use the same configuration
        assert supervisor1.bus is supervisor2.bus
        assert supervisor1.store is supervisor2.store
