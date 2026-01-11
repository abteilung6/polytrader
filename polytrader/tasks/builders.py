"""Builder for paper trading system components.

Per architecture.mdc: Encapsulates factory creation and dependency wiring
for paper trading mode.
"""

from collections.abc import Callable
from typing import TYPE_CHECKING

from polytrader.adapters import create_adapter_factory
from polytrader.config import PolymarketSecrets
from polytrader.events import EventBus
from polytrader.execution import ExecutionRouter
from polytrader.execution.fill_models import FillModel
from polytrader.execution.paper import PaperExecutionAdapter
from polytrader.market_discovery import MarketDiscoveryService
from polytrader.observer import create_observer_factory
from polytrader.oms import InMemoryOrderStore, OMSCore
from polytrader.oms.idempotency import IdempotencyStore
from polytrader.portfolio import PortfolioService
from polytrader.position_manager import IPositionManager
from polytrader.position_manager.paper import PaperPositionManager
from polytrader.risk import RiskChecker, RiskEngine, get_default_limits
from polytrader.store import IMarketDataStore
from polytrader.strategies import create_simple_threshold_factory
from polytrader.supervisor import MarketSupervisor, SystemSupervisor

if TYPE_CHECKING:
    from polytrader.adapters import IMarketDataAdapter
    from polytrader.observer import IObserver
    from polytrader.strategies import IStrategy


class PaperTradingSystemBuilder:
    """Builder for paper trading system components.

    Encapsulates the creation of all factories and supervisors needed for
    paper trading mode. Manages shared dependencies (e.g., shared OMS store)
    and ensures correct wiring between components.

    Per flows.mdc:
    - Creates factories for all system services
    - Manages shared OMS store between OMSCore and PaperPositionManager
    - Builds SystemSupervisor and MarketSupervisor with proper dependencies
    """

    def __init__(
        self,
        bus: EventBus,
        store: IMarketDataStore,
        discovery: MarketDiscoveryService,
        market_pattern: str,
        frequency: float,
    ) -> None:
        """Initialize the builder with core dependencies.

        Args:
            bus: Event bus for communication
            store: Market data store
            discovery: Market discovery service
            market_pattern: Market pattern (e.g., 'btc-updown-15m')
            frequency: Polling frequency in Hz

        Raises:
            ValueError: If frequency <= 0 or market_pattern is empty
        """
        if frequency <= 0.0:
            raise ValueError(f"frequency must be > 0, got {frequency}")
        if not market_pattern:
            raise ValueError("market_pattern cannot be empty")

        self._bus = bus
        self._store = store
        self._discovery = discovery
        self._market_pattern = market_pattern
        self._frequency = frequency

        # Configuration (set via builder methods)
        self._buy_threshold: float = 0.30
        self._min_history: int = 30
        self._size: float = 1.0
        self._fill_model: FillModel = FillModel.MID_PRICE
        self._fill_probability: float = 1.0
        self._rejection_probability: float = 0.0
        self._latency_ms: float = 50.0
        self._starting_equity: float = 1000.0

        # Shared dependencies (created on first access)
        self._shared_oms_store: InMemoryOrderStore | None = None
        self._secrets: PolymarketSecrets | None = None
        self._adapter_factory: Callable[[str], IMarketDataAdapter] | None = None
        self._observer_factory: Callable[[IMarketDataAdapter], IObserver] | None = None
        self._strategy_factory: Callable[[str], IStrategy] | None = None

    def strategy_config(
        self,
        buy_threshold: float = 0.30,
        min_history: int = 30,
    ) -> "PaperTradingSystemBuilder":
        """Configure strategy parameters.

        Args:
            buy_threshold: Buy threshold price (0-1)
            min_history: Minimum history ticks required

        Returns:
            Self for fluent interface

        Raises:
            ValueError: If parameters are invalid
        """
        if not 0.0 <= buy_threshold <= 1.0:
            raise ValueError(f"buy_threshold must be between 0 and 1, got {buy_threshold}")
        if min_history < 0:
            raise ValueError(f"min_history must be >= 0, got {min_history}")

        self._buy_threshold = buy_threshold
        self._min_history = min_history
        return self

    def execution_config(
        self,
        size: float = 1.0,
        fill_model: FillModel = FillModel.MID_PRICE,
        fill_probability: float = 1.0,
        rejection_probability: float = 0.0,
        latency_ms: float = 50.0,
    ) -> "PaperTradingSystemBuilder":
        """Configure execution parameters.

        Args:
            size: Trade size in USD
            fill_model: Fill simulation model
            fill_probability: Probability of fill (0-1)
            rejection_probability: Probability of rejection (0-1)
            latency_ms: Simulated latency in milliseconds

        Returns:
            Self for fluent interface

        Raises:
            ValueError: If parameters are invalid
        """
        if size <= 0.0:
            raise ValueError(f"size must be > 0, got {size}")
        if not 0.0 <= fill_probability <= 1.0:
            raise ValueError(f"fill_probability must be between 0 and 1, got {fill_probability}")
        if not 0.0 <= rejection_probability <= 1.0:
            raise ValueError(
                f"rejection_probability must be between 0 and 1, got {rejection_probability}"
            )
        if fill_probability + rejection_probability > 1.0:
            raise ValueError(
                f"fill_probability + rejection_probability must be <= 1.0, "
                f"got {fill_probability + rejection_probability}"
            )
        if latency_ms < 0.0:
            raise ValueError(f"latency_ms must be >= 0, got {latency_ms}")

        self._size = size
        self._fill_model = fill_model
        self._fill_probability = fill_probability
        self._rejection_probability = rejection_probability
        self._latency_ms = latency_ms
        return self

    def position_config(self, starting_equity: float = 1000.0) -> "PaperTradingSystemBuilder":
        """Configure position management parameters.

        Args:
            starting_equity: Starting equity in USD

        Returns:
            Self for fluent interface

        Raises:
            ValueError: If starting_equity <= 0
        """
        if starting_equity <= 0.0:
            raise ValueError(f"starting_equity must be > 0, got {starting_equity}")

        self._starting_equity = starting_equity
        return self

    def _get_shared_oms_store(self) -> InMemoryOrderStore:
        """Get or create shared OMS store.

        Returns:
            Shared OMS store instance
        """
        if self._shared_oms_store is None:
            self._shared_oms_store = InMemoryOrderStore(self._bus)
        return self._shared_oms_store

    def _get_secrets(self) -> PolymarketSecrets:
        """Get or create secrets for adapter factory.

        Returns:
            Polymarket secrets instance
        """
        if self._secrets is None:
            self._secrets = PolymarketSecrets()
        return self._secrets

    def _get_adapter_factory(self) -> Callable[[str], IMarketDataAdapter]:
        """Get or create adapter factory.

        Returns:
            Adapter factory function
        """
        if self._adapter_factory is None:
            secrets = self._get_secrets()
            self._adapter_factory = create_adapter_factory(
                secrets, polling_frequency_hz=self._frequency
            )
        return self._adapter_factory

    def _get_observer_factory(self) -> Callable[[IMarketDataAdapter], IObserver]:
        """Get or create observer factory.

        Returns:
            Observer factory function
        """
        if self._observer_factory is None:
            self._observer_factory = create_observer_factory(self._bus, self._store)
        return self._observer_factory

    def _get_strategy_factory(self) -> Callable[[str], IStrategy]:
        """Get or create strategy factory.

        Returns:
            Strategy factory function
        """
        if self._strategy_factory is None:
            self._strategy_factory = create_simple_threshold_factory(
                store=self._store,
                buy_threshold=self._buy_threshold,
                min_history=self._min_history,
            )
        return self._strategy_factory

    def _create_execution_router_factory(self) -> Callable[[], ExecutionRouter]:
        """Create execution router factory.

        Returns:
            Factory function for ExecutionRouter
        """

        def factory() -> ExecutionRouter:
            adapter = PaperExecutionAdapter(
                bus=self._bus,
                store=self._store,
                fill_model=self._fill_model,
                fill_probability=self._fill_probability,
                rejection_probability=self._rejection_probability,
                latency_ms=self._latency_ms,
            )
            return ExecutionRouter(bus=self._bus, adapter=adapter)

        return factory

    def _create_position_manager_factory(self) -> Callable[[], IPositionManager]:
        """Create position manager factory.

        Returns:
            Factory function for PaperPositionManager
        """
        shared_store = self._get_shared_oms_store()

        def factory() -> IPositionManager:
            return PaperPositionManager(
                bus=self._bus, store=shared_store, starting_equity=self._starting_equity
            )

        return factory

    def _create_portfolio_service_factory(
        self, position_manager_factory: Callable[[], IPositionManager]
    ) -> Callable[[], PortfolioService]:
        """Create portfolio service factory.

        Args:
            position_manager_factory: Factory for position manager

        Returns:
            Factory function for PortfolioService
        """

        def factory() -> PortfolioService:
            position_manager = position_manager_factory()
            return PortfolioService(
                bus=self._bus,
                store=self._store,
                position_manager=position_manager,
                fixed_size_usd=self._size,
            )

        return factory

    def _create_risk_checker_factory(self) -> Callable[[], RiskChecker]:
        """Create risk checker factory.

        Returns:
            Factory function for RiskChecker
        """

        def factory() -> RiskChecker:
            risk_limits = get_default_limits()
            risk_engine = RiskEngine(limits=risk_limits)
            return RiskChecker(bus=self._bus, engine=risk_engine, store=self._store)

        return factory

    def _create_oms_core_factory(self) -> Callable[[], OMSCore]:
        """Create OMS core factory.

        Returns:
            Factory function for OMSCore
        """
        shared_store = self._get_shared_oms_store()

        def factory() -> OMSCore:
            idempotency_store = IdempotencyStore()
            return OMSCore(bus=self._bus, store=shared_store, idempotency_store=idempotency_store)

        return factory

    def build_system_supervisor(self) -> SystemSupervisor:
        """Build SystemSupervisor with all required factories.

        Returns:
            Configured SystemSupervisor instance

        Raises:
            ValueError: If configuration is invalid
        """
        position_manager_factory = self._create_position_manager_factory()
        portfolio_service_factory = self._create_portfolio_service_factory(position_manager_factory)
        risk_checker_factory = self._create_risk_checker_factory()
        oms_core_factory = self._create_oms_core_factory()
        execution_router_factory = self._create_execution_router_factory()

        return SystemSupervisor(
            bus=self._bus,
            store=self._store,
            portfolio_service_factory=portfolio_service_factory,
            risk_checker_factory=risk_checker_factory,
            oms_core_factory=oms_core_factory,
            execution_router_factory=execution_router_factory,
            position_manager_factory=position_manager_factory,
        )

    def build_market_supervisor(
        self, position_manager: IPositionManager | None = None
    ) -> MarketSupervisor:
        """Build MarketSupervisor with all required factories.

        Args:
            position_manager: Position manager instance (from SystemSupervisor)

        Returns:
            Configured MarketSupervisor instance
        """
        adapter_factory = self._get_adapter_factory()
        observer_factory = self._get_observer_factory()
        strategy_factory = self._get_strategy_factory()

        return MarketSupervisor(
            pattern=self._market_pattern,
            discovery_service=self._discovery,
            adapter_factory=adapter_factory,
            observer_factory=observer_factory,
            strategy_factory=strategy_factory,
            bus=self._bus,
            store=self._store,
            position_manager=position_manager,
        )

    def build_complete_system(
        self,
    ) -> tuple[SystemSupervisor, MarketSupervisor]:
        """Build both supervisors with proper wiring.

        Returns:
            Tuple of (SystemSupervisor, MarketSupervisor)

        Note:
            SystemSupervisor must be started before MarketSupervisor
            to get the position manager instance.
        """
        system_supervisor = self.build_system_supervisor()
        # Position manager will be available after system_supervisor.start()
        # For now, pass None - caller must get it from system_supervisor after start()
        market_supervisor = self.build_market_supervisor(position_manager=None)
        return system_supervisor, market_supervisor
