"""Platform task: Start multi-strategy platform with control plane.

Per Platform_Proposal.md §4.1: Platform task starts:
- PlatformOrchestrator (loads strategies, creates runners)
- ControlPlaneService (processes control commands)
- FastAPI control API server
- All strategies run in paper mode

Per docs/analysis-why-no-signals-in-api.md: Events are persisted to PostgreSQL
via EventSink so the Control API (which reads from the same DB) can return
signals and other events. If database config is missing or EventSink init
fails, the platform continues without event persistence (events only in-memory
to subscribers).
"""

import asyncio
import signal
from collections.abc import Callable
from pathlib import Path

import uvicorn
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from polytrader.adapters import create_adapter_factory
from polytrader.api.app import create_app
from polytrader.clob import create_clob_client_factory
from polytrader.config import PolymarketSecrets, get_database_url
from polytrader.config.loader import load_platform_config
from polytrader.config.models import PlatformConfig
from polytrader.events import (
    CANCEL_ORDER_COMMANDS_LIVE,
    SUBMIT_ORDER_COMMANDS_LIVE,
    SYSTEM_LIFECYCLE,
    EventBus,
)
from polytrader.events.closed_trade_sink import ClosedTradeSink
from polytrader.events.sink import EventSink
from polytrader.events.stores import PostgreSQLEventStore
from polytrader.events.types import SystemStartedEvent
from polytrader.execution import ExecutionRouter, create_execution_router_factory
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
from polytrader.platform.registry import StrategyRegistry
from polytrader.position_manager.paper import PaperPositionManager
from polytrader.store_factory import create_market_data_store


async def platform_start_task(
    config_path: Path | None = None,
    secrets: PolymarketSecrets | None = None,
    platform_config: PlatformConfig | None = None,
) -> None:
    """Start the platform with orchestrator, control plane, and API server.

    Per Platform_Proposal.md §4.1:
    - Starts PlatformOrchestrator (loads strategies from DB, creates runners)
    - Starts ControlPlaneService (processes control commands)
    - Starts FastAPI control API server
    - All strategies run in paper mode

    All settings come from the YAML config file or PlatformConfig defaults.
    No CLI override parameters — use the config file to change values.

    Args:
        config_path: Path to platform config YAML file (optional).
        secrets: Polymarket secrets (defaults to loading from env).
        platform_config: Pre-loaded PlatformConfig (for testing; skips file loading).
    """
    if secrets is None:
        secrets = PolymarketSecrets()

    # --- Load platform config ---
    bus = EventBus()

    if platform_config is not None:
        pcfg = platform_config
    else:
        pcfg = await load_platform_config(config_path, bus=bus)

    # All values from config (no CLI overrides)
    api_host = pcfg.api.host
    api_port = pcfg.api.port
    frequency = pcfg.market_data.polling_frequency_hz
    starting_equity = pcfg.portfolio.starting_equity

    logger.info(
        "Platform config loaded (version={version})",
        version=pcfg.version,
    )

    # Initialize core infrastructure
    store = create_market_data_store(enable_postgres=True)
    discovery = MarketDiscoveryService(bus=bus)

    # Create database engine and session factory
    db_url = get_database_url()
    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+psycopg://", 1)

    engine = create_async_engine(db_url, echo=False)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    # EventSink: persist events to PostgreSQL so Control API can read signals/orders
    event_sink: EventSink | None = None
    event_sink_task: asyncio.Task[None] | None = None
    postgres_event_store: PostgreSQLEventStore | None = None
    try:
        postgres_event_store = PostgreSQLEventStore(
            connection_url=db_url, pool_size=pcfg.database.event_store_pool_size
        )
        await postgres_event_store.initialize()
        event_sink = EventSink(bus=bus, store=postgres_event_store)
        event_sink_task = asyncio.create_task(event_sink.run())
        logger.info("EventSink started (events persisted to PostgreSQL)")
    except Exception as e:
        logger.warning(
            "EventSink not started (events in-memory only): {error}",
            error=str(e),
            error_type=type(e).__name__,
        )
        event_sink = None
        event_sink_task = None
        postgres_event_store = None

    # ClosedTradeSink: project StrategyClosedTradeEvent to dedicated read-model table
    closed_trade_sink: ClosedTradeSink | None = None
    closed_trade_sink_task: asyncio.Task[None] | None = None
    try:
        closed_trade_sink = ClosedTradeSink(bus=bus, session_factory=Session)
        closed_trade_sink_task = asyncio.create_task(closed_trade_sink.run())
        logger.info("ClosedTradeSink started (closed trades persisted to strategy_closed_trades)")
    except Exception as e:
        logger.warning(
            "ClosedTradeSink not started: {error}",
            error=str(e),
            error_type=type(e).__name__,
        )
        closed_trade_sink = None
        closed_trade_sink_task = None

    # Emit system started event (will be persisted if EventSink is running)
    started_event = SystemStartedEvent()
    await bus.publish(SYSTEM_LIFECYCLE, started_event)

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

    # In-memory set of active strategy IDs (proposal router + live execution read this)
    active_strategies: set[str] = set()

    # Live execution router factory (only when config + credentials allow)
    live_execution_router_factory: Callable[[], ExecutionRouter] | None = None
    if pcfg.execution.live_lane_enabled and secrets.has_live_credentials():
        clob_factory = create_clob_client_factory(secrets, pcfg)
        live_execution_router_factory = create_execution_router_factory(
            bus=bus,
            clob_client_factory=clob_factory,
            execution_control=execution_control,
            active_strategies=active_strategies,
            is_paper_mode=False,
            submit_commands_topic=SUBMIT_ORDER_COMMANDS_LIVE,
            cancel_commands_topic=CANCEL_ORDER_COMMANDS_LIVE,
        )
        logger.info("Live execution lane enabled (credentials present)")
    else:
        if pcfg.execution.live_lane_enabled and not secrets.has_live_credentials():
            logger.warning(
                "Live lane enabled in config but credentials missing or incomplete; "
                "running paper-only"
            )

    # Create platform orchestrator; keep session for full run so add_strategy works
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
            platform_config=pcfg,
            execution_control=execution_control,
            get_active_strategies=lambda: active_strategies,
            live_execution_router_factory=live_execution_router_factory,
        )

        # Start orchestrator (loads strategies, creates runners)
        await orchestrator.start()

        # Control plane service needs its own session for polling
        control_session = Session()
        try:
            command_repo = ControlCommandRepository(control_session)
            execution_repo = ExecutionControlRepository(control_session)
            live_repo = LiveStrategyRepository(control_session)
            strategy_registry = StrategyRegistry(control_session)

            # Create control plane service (updates active_strategies on add/remove commands)
            control_plane_service = ControlPlaneService(
                command_repo=command_repo,
                execution_repo=execution_repo,
                live_repo=live_repo,
                strategy_registry=strategy_registry,
                execution_control=execution_control,
                bus=bus,
                poll_interval_s=pcfg.supervisor.control_plane_poll_interval_s,
                active_strategies=active_strategies,
            )

            # Start control plane service
            await control_plane_service.start()

            # Start FastAPI server in background; inject runtime state for API endpoints
            app = create_app()
            app.state.orchestrator = orchestrator
            app.state.execution_control = execution_control
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
            metrics_port = pcfg.metrics.port
            start_metrics_server(port=metrics_port, config=metrics_config)

            logger.info("🚀 Platform started")
            logger.info("Control API: http://{host}:{port}/docs", host=api_host, port=api_port)
            logger.info(
                "Metrics server: http://{host}:{port}/metrics",
                host="localhost",
                port=metrics_port,
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

                # Stop ClosedTradeSink
                if closed_trade_sink_task is not None:
                    if closed_trade_sink is not None:
                        await closed_trade_sink.stop()
                    closed_trade_sink_task.cancel()
                    try:
                        await asyncio.wait_for(closed_trade_sink_task, timeout=5.0)
                    except (asyncio.CancelledError, TimeoutError):
                        pass
                    closed_trade_sink_task = None

                # Stop EventSink and cleanup PostgreSQL event store
                if event_sink_task is not None:
                    if event_sink is not None:
                        await event_sink.stop()
                    event_sink_task.cancel()
                    try:
                        await asyncio.wait_for(event_sink_task, timeout=5.0)
                    except (asyncio.CancelledError, TimeoutError):
                        pass
                    event_sink_task = None
                if postgres_event_store is not None:
                    try:
                        await postgres_event_store.cleanup()
                    except Exception as e:
                        logger.exception(
                            "Error cleaning up event store: {error}",
                            error=str(e),
                        )
                    postgres_event_store = None

                # Close control plane session
                await control_session.close()

                # Close database engine
                await engine.dispose()

                logger.info("Platform stopped")
        except Exception:
            # Stop ClosedTradeSink on error
            if closed_trade_sink_task is not None and closed_trade_sink is not None:
                try:
                    await closed_trade_sink.stop()
                except Exception:
                    pass
                closed_trade_sink_task.cancel()
                try:
                    await closed_trade_sink_task
                except asyncio.CancelledError:
                    pass
            # Stop EventSink and cleanup on error
            if event_sink_task is not None and event_sink is not None:
                try:
                    await event_sink.stop()
                except Exception:
                    pass
                event_sink_task.cancel()
                try:
                    await event_sink_task
                except asyncio.CancelledError:
                    pass
            if postgres_event_store is not None:
                try:
                    await postgres_event_store.cleanup()
                except Exception:
                    pass
            # Close control plane session on error
            await control_session.close()
            # Close database engine on error
            await engine.dispose()
            raise
