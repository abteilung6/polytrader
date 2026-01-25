"""Platform task: Start multi-strategy platform with control plane.

Per Platform_Proposal.md §4.1: Platform task starts:
- PlatformOrchestrator (loads strategies, creates runners)
- ControlPlaneService (processes control commands)
- FastAPI control API server
- All strategies run in paper mode
"""

import asyncio
import signal

import uvicorn
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from polytrader.adapters import create_adapter_factory
from polytrader.api.app import create_app
from polytrader.config import PolymarketSecrets, get_database_url
from polytrader.events import SYSTEM_LIFECYCLE, EventBus
from polytrader.events.store import MemoryEventStore
from polytrader.events.types import SystemStartedEvent
from polytrader.logging_config import logger
from polytrader.market_discovery import MarketDiscoveryService
from polytrader.observer import create_observer_factory
from polytrader.oms.store import InMemoryOrderStore
from polytrader.ops.control import ExecutionControl
from polytrader.platform.control import (
    ControlCommandRepository,
    ExecutionControlRepository,
    LiveStrategyRepository,
)
from polytrader.platform.control_plane import ControlPlaneService
from polytrader.platform.orchestrator import PlatformOrchestrator
from polytrader.position_manager.paper import PaperPositionManager
from polytrader.store_factory import create_market_data_store


async def platform_start_task(
    api_host: str = "0.0.0.0",
    api_port: int = 8000,
    frequency: float = 1.0,
    starting_equity: float = 1000.0,
    secrets: PolymarketSecrets | None = None,
) -> None:
    """Start the platform with orchestrator, control plane, and API server.

    Per Platform_Proposal.md §4.1:
    - Starts PlatformOrchestrator (loads strategies from DB, creates runners)
    - Starts ControlPlaneService (processes control commands)
    - Starts FastAPI control API server
    - All strategies run in paper mode

    Args:
        api_host: API server host (default: "0.0.0.0")
        api_port: API server port (default: 8000)
        frequency: Market data polling frequency in Hz (default: 1.0)
        starting_equity: Starting equity for paper trading (default: 1000.0)
        secrets: Polymarket secrets (defaults to loading from env)
    """
    if secrets is None:
        secrets = PolymarketSecrets()

    # Initialize core infrastructure
    store = create_market_data_store(enable_postgres=True)
    event_store = MemoryEventStore()
    bus = EventBus(store=event_store)
    discovery = MarketDiscoveryService(bus=bus)

    # Emit system started event
    started_event = SystemStartedEvent()
    await bus.publish(SYSTEM_LIFECYCLE, started_event)

    # Create database engine and session factory
    db_url = get_database_url()
    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+psycopg://", 1)

    engine = create_async_engine(db_url, echo=False)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    # Create factories for orchestrator
    adapter_factory = create_adapter_factory(secrets, polling_frequency_hz=frequency)
    observer_factory = create_observer_factory(bus, store)

    # Create paper position manager (shared across strategies)
    # PaperPositionManager needs an OMS store, but it's optional
    oms_store_paper = InMemoryOrderStore(bus=bus)
    position_manager = PaperPositionManager(
        bus=bus,
        store=oms_store_paper,
        starting_equity=starting_equity,
    )

    # Create execution control for control plane
    execution_control = ExecutionControl(bus=bus)

    # Create platform orchestrator (needs session for loading strategies)
    # Session is only used during start() to load strategies
    async with Session() as orchestrator_session:
        orchestrator = PlatformOrchestrator(
            bus=bus,
            store=store,
            session=orchestrator_session,
            discovery_service=discovery,
            adapter_factory=adapter_factory,
            observer_factory=observer_factory,
            position_manager=position_manager,
            paper_oms_store=oms_store_paper,
        )

        # Start orchestrator (loads strategies, creates runners)
        await orchestrator.start()

    # Create repositories for control plane service
    # Control plane service needs persistent session for polling
    control_session = Session()
    try:
        command_repo = ControlCommandRepository(control_session)
        execution_repo = ExecutionControlRepository(control_session)
        live_repo = LiveStrategyRepository(control_session)

        # Create control plane service
        control_plane_service = ControlPlaneService(
            command_repo=command_repo,
            execution_repo=execution_repo,
            live_repo=live_repo,
            execution_control=execution_control,
            bus=bus,
            poll_interval_s=1.0,
        )

        # Start control plane service
        await control_plane_service.start()

        # Start FastAPI server in background
        app = create_app()
        config = uvicorn.Config(
            app=app,
            host=api_host,
            port=api_port,
            log_level="info",
        )
        server = uvicorn.Server(config)

        # Start server in background task
        server_task = asyncio.create_task(server.serve())

        # Start dedicated metrics server on separate port
        from polytrader.config import MetricsConfig
        from polytrader.obs.metrics_server import start_metrics_server

        metrics_config = MetricsConfig()
        start_metrics_server(port=metrics_config.metrics_port, config=metrics_config)
        logger.info("Metrics server started on port {port}", port=metrics_config.metrics_port)

        logger.info("🚀 Platform started")
        logger.info("Control API: http://{host}:{port}/docs", host=api_host, port=api_port)
        logger.info(
            "Metrics server: http://{host}:{port}/metrics",
            host="localhost",
            port=metrics_config.metrics_port,
        )
        logger.info("Press Ctrl+C to stop")

        try:
            # Wait for shutdown signal
            shutdown_event = asyncio.Event()

            def signal_handler() -> None:
                logger.info("Shutdown signal received")
                shutdown_event.set()

            # Register signal handlers
            loop = asyncio.get_event_loop()
            for sig in (signal.SIGINT, signal.SIGTERM):
                loop.add_signal_handler(sig, signal_handler)

            # Wait for shutdown
            await shutdown_event.wait()

        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received")
        finally:
            # Graceful shutdown
            logger.info("Shutting down platform...")

            # Stop server
            server.should_exit = True
            server_task.cancel()
            try:
                await server_task
            except asyncio.CancelledError:
                pass

            # Stop control plane service
            await control_plane_service.stop()

            # Stop orchestrator
            await orchestrator.stop()

            # Close control plane session
            await control_session.close()

            # Close database engine
            await engine.dispose()

            logger.info("Platform stopped")
    except Exception:
        # Close control plane session on error
        await control_session.close()
        # Close database engine on error
        await engine.dispose()
        raise
