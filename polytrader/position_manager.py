"""Position manager for tracking and monitoring trading positions."""

import asyncio
from collections.abc import Callable
from typing import Any, Protocol

from polytrader.clob import ExternalOrder, IClobClientFactory, get_active_orders
from polytrader.events import ORDERS, PROPOSALS, TICKS, EventBus
from polytrader.gamma import GammaClient
from polytrader.logging_config import logger
from polytrader.types import MarketTick, Order, Outcome, Position, TradeProposal


class IPositionManager(Protocol):
    """Protocol for position manager components."""

    async def run(self) -> None:
        """Start the position manager."""
        ...

    def stop(self) -> None:
        """Stop the position manager."""
        ...


def create_position_manager_factory(
    bus: EventBus,
    clob_client_factory: IClobClientFactory,
    gamma_client: GammaClient | None = None,
    sync_interval: float = 60.0,
) -> Callable[[], IPositionManager]:
    """Create a factory function for PositionManager.

    Args:
        bus: Event bus for subscribing to orders and ticks, publishing proposals
        clob_client_factory: Factory for creating CLOB clients
        gamma_client: Gamma client for market lookups (defaults to new instance)
        sync_interval: How often to sync with external API (seconds, 0 to disable)

    Returns:
        Factory function that returns a PositionManager
    """

    def factory() -> IPositionManager:
        return PositionManager(
            bus=bus,
            clob_client_factory=clob_client_factory,
            gamma_client=gamma_client or GammaClient(),
            sync_interval=sync_interval,
        )

    return factory


class PositionManager(IPositionManager):
    """Manages trading positions, monitors prices, and generates sell proposals.

    Tracks positions from executed BUY orders, monitors market ticks for target
    prices, and automatically generates SELL proposals when targets are reached.
    Also periodically syncs with external API to reconcile positions.
    """

    def __init__(
        self,
        bus: EventBus,
        clob_client_factory: IClobClientFactory,
        gamma_client: GammaClient,
        sync_interval: float = 60.0,
    ) -> None:
        """Initialize the position manager.

        Args:
            bus: Event bus for subscribing to orders and ticks, publishing proposals
            clob_client_factory: Factory for creating CLOB clients
            gamma_client: Gamma client for market lookups
            sync_interval: How often to sync with external API (seconds, 0 to disable)
        """
        self.bus = bus
        self.clob_client_factory = clob_client_factory
        self.gamma_client = gamma_client
        self.sync_interval = sync_interval

        # Internal position tracking: (market_slug, outcome) -> Position
        self._positions: dict[tuple[str, Outcome], Position] = {}

        # Track order IDs for reconciliation: order_id -> (market_slug, outcome)
        self._order_id_to_position: dict[str, tuple[str, Outcome]] = {}

        # Token ID to market mapping for external order reconciliation
        # token_id -> (market_slug, outcome)
        self._token_to_market: dict[str, tuple[str, Outcome]] = {}

        self._running = False

    async def run(self) -> None:
        """Start the position manager."""
        self._running = True
        logger.info("Starting PositionManager")

        # Subscribe to orders and ticks
        orders_queue = self.bus.subscribe(ORDERS)
        ticks_queue = self.bus.subscribe(TICKS)

        # Start sync task if enabled
        sync_task: asyncio.Task | None = None
        if self.sync_interval > 0:
            sync_task = asyncio.create_task(self._periodic_sync())

        try:
            # Initial sync on startup
            if self.sync_interval > 0:
                await self._sync_with_external()

            # Process orders and ticks
            while self._running:
                # Wait for either an order or a tick
                done, pending = await asyncio.wait(
                    [
                        asyncio.create_task(orders_queue.get()),
                        asyncio.create_task(ticks_queue.get()),
                    ],
                    return_when=asyncio.FIRST_COMPLETED,
                )

                # Handle completed tasks
                for task in done:
                    try:
                        result = await task
                        if isinstance(result, Order):
                            await self._handle_order(result)
                        elif isinstance(result, MarketTick):
                            await self._check_target_prices(result)
                    except Exception:
                        logger.exception("Error processing order or tick")

                # Cancel pending tasks
                for task in pending:
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass

        except Exception:
            logger.exception("PositionManager error")
            raise
        finally:
            self._running = False
            if sync_task:
                sync_task.cancel()
                try:
                    await sync_task
                except asyncio.CancelledError:
                    pass

    async def _handle_order(self, order: Order) -> None:
        """Handle an executed order.

        Creates positions from BUY orders and removes positions from SELL orders.
        """
        key = (order.market_slug, order.outcome)

        if order.side == "BUY":
            # Create position from BUY order
            if key in self._positions:
                logger.bind(market_slug=order.market_slug, outcome=order.outcome).warning(
                    "Position already exists, updating"
                )

            order_id = (
                order.response.get("order_id") or order.response.get("id", "unknown")
                if isinstance(order.response, dict)
                else "unknown"
            )

            # Get entry price from response or use a default
            entry_price = 0.5  # Default mid-price
            if isinstance(order.response, dict):
                # Try to extract fill price from response
                fill_price = order.response.get("fill_price") or order.response.get("price")
                if fill_price:
                    entry_price = float(fill_price)

            position = Position(
                market_slug=order.market_slug,
                outcome=order.outcome,
                size=order.size,
                target_price=order.target_price if order.target_price is not None else 0.5,
                entry_price=entry_price,
                entry_time=order.ts,
                order_id=order_id if order_id != "unknown" else None,
            )

            self._positions[key] = position
            self._order_id_to_position[order_id] = key

            # Store token_id mapping for external order reconciliation
            await self._cache_token_id(order.market_slug, order.outcome)

            logger.bind(
                market_slug=order.market_slug,
                outcome=order.outcome,
                target_price=position.target_price,
            ).info(
                "Position opened: {market_slug}/{outcome} size=${size} target={target_price}",
                market_slug=order.market_slug,
                outcome=order.outcome,
                size=order.size,
                target_price=position.target_price,
            )

        elif order.side == "SELL":
            # Remove position from SELL order
            if key in self._positions:
                position = self._positions.pop(key)
                logger.bind(market_slug=order.market_slug, outcome=order.outcome).info(
                    "Position closed: {market_slug}/{outcome}",
                    market_slug=order.market_slug,
                    outcome=order.outcome,
                )

                # Clean up order ID mapping
                order_id = (
                    order.response.get("order_id") or order.response.get("id", "unknown")
                    if isinstance(order.response, dict)
                    else "unknown"
                )
                if order_id in self._order_id_to_position:
                    del self._order_id_to_position[order_id]
            else:
                logger.bind(market_slug=order.market_slug, outcome=order.outcome).debug(
                    "SELL order for position we don't track (may be external)"
                )

    async def _check_target_prices(self, tick: MarketTick) -> None:
        """Check if any positions have reached their target price.

        Generates SELL proposals when target prices are reached.
        """
        key = (tick.market_slug, tick.outcome)

        if key not in self._positions:
            return

        position = self._positions[key]
        mid_price = tick.mid

        # Check if target price is reached (for BUY positions, sell when price >= target)
        if mid_price >= position.target_price:
            logger.bind(
                market_slug=tick.market_slug,
                outcome=tick.outcome,
                current_price=mid_price,
                target_price=position.target_price,
            ).info(
                "Target price reached: {current_price:.4f} >= {target_price:.4f} "
                "for {market_slug}/{outcome}",
                current_price=mid_price,
                target_price=position.target_price,
                market_slug=tick.market_slug,
                outcome=tick.outcome,
            )

            # Generate SELL proposal
            proposal = TradeProposal(
                ts=tick.ts,
                market_slug=tick.market_slug,
                outcome=tick.outcome,
                side="SELL",
                target_price=position.target_price,
                limit_price=tick.best_bid,
                size=position.size,
                reason=(
                    f"Target price reached: {mid_price:.4f} >= {position.target_price:.4f} "
                    f"(entry: {position.entry_price:.4f})"
                ),
            )

            await self.bus.publish(PROPOSALS, proposal)

            logger.bind(
                market_slug=tick.market_slug,
                outcome=tick.outcome,
                price=mid_price,
            ).info(
                "Published SELL proposal: target reached at {price:.4f}",
                price=mid_price,
            )

    async def _periodic_sync(self) -> None:
        """Periodically sync with external API."""
        while self._running:
            await asyncio.sleep(self.sync_interval)
            try:
                await self._sync_with_external()
            except Exception:
                logger.exception("Error in periodic sync")

    async def _sync_with_external(self) -> None:
        """Sync internal positions with external API state."""
        logger.debug("Syncing positions with external API")

        try:
            client = self.clob_client_factory()

            # Get all active orders from external API
            external_orders = await asyncio.to_thread(lambda: get_active_orders(client))

            # Reconcile with internal positions
            await self._reconcile_positions(external_orders)

        except Exception:
            logger.exception("Error syncing with external API")

    async def _cache_token_id(self, market_slug: str, outcome: Outcome) -> None:
        """Cache token_id for a market/outcome pair.

        This enables reverse lookup from external orders (which have token_id)
        to our internal positions (which use market_slug/outcome).

        Args:
            market_slug: Market slug
            outcome: Outcome ("UP" or "DOWN")
        """
        try:
            market = await asyncio.to_thread(self.gamma_client.get_market_by_slug, market_slug)
            token_id = market.get_token_id(outcome)
            self._token_to_market[token_id] = (market_slug, outcome)
            logger.bind(market_slug=market_slug, outcome=outcome, token_id=token_id).debug(
                "Cached token_id {token_id} for {market_slug}/{outcome}",
                token_id=token_id,
                market_slug=market_slug,
                outcome=outcome,
            )
        except Exception:
            logger.exception(
                "Failed to cache token_id for {market_slug}/{outcome}",
                market_slug=market_slug,
                outcome=outcome,
            )

    def _parse_external_order(self, order_data: dict[str, Any]) -> ExternalOrder | None:
        """Parse external order and extract relevant information.

        Args:
            order_data: Raw order dictionary from Polymarket API

        Returns:
            ExternalOrder if parseable, None otherwise
        """
        return ExternalOrder.from_api_response(order_data)

    def _get_market_from_token(self, token_id: str) -> tuple[str, Outcome] | None:
        """Get market_slug and outcome from token_id.

        Uses the internal cache. Returns None if token_id not found in cache.

        Args:
            token_id: Token ID from external order

        Returns:
            Tuple of (market_slug, outcome) if found, None otherwise
        """
        return self._token_to_market.get(token_id)

    async def _reconcile_positions(self, external_orders: list[dict[str, Any]]) -> None:
        """Reconcile internal positions with external orders.

        Args:
            external_orders: List of order dictionaries from external API

        This implementation:
        1. Parses external orders to extract token_id and status
        2. Maps token_id to (market_slug, outcome) using cache
        3. Compares external orders with internal positions
        4. Logs discrepancies for manual review
        """
        # Step 1: Parse external orders
        parsed_orders = []
        for order_data in external_orders:
            parsed = self._parse_external_order(order_data)
            if parsed:
                parsed_orders.append(parsed)

        if not parsed_orders:
            logger.debug("No parseable external orders found")
            return

        logger.debug("Parsed {count} external orders", count=len(parsed_orders))

        # Step 2: Map token_ids to (market_slug, outcome) and group by position
        external_positions: dict[tuple[str, Outcome], list[ExternalOrder]] = {}
        unknown_tokens: list[str] = []

        for parsed in parsed_orders:
            token_id = parsed.token_id
            market_info = self._get_market_from_token(token_id)

            if market_info:
                market_slug, outcome = market_info
                key = (market_slug, outcome)
                external_positions.setdefault(key, []).append(parsed)
            else:
                unknown_tokens.append(token_id)

        if unknown_tokens:
            logger.debug(
                "Found {count} external orders with unknown token_ids (not in cache)",
                count=len(unknown_tokens),
            )

        # Step 3: Compare external orders with internal positions
        for key, external_orders_list in external_positions.items():
            market_slug, outcome = key
            has_internal_position = key in self._positions

            # Find most relevant external order (prefer FILLED, then most recent)
            filled_orders = [o for o in external_orders_list if o.status == "FILLED"]
            cancelled_orders = [o for o in external_orders_list if o.status == "CANCELLED"]
            open_orders = [o for o in external_orders_list if o.status == "OPEN"]

            if filled_orders:
                # External order is FILLED
                if has_internal_position:
                    logger.bind(market_slug=market_slug, outcome=outcome).debug(
                        "Position {market_slug}/{outcome} confirmed by external FILLED order",
                        market_slug=market_slug,
                        outcome=outcome,
                    )
                else:
                    logger.bind(market_slug=market_slug, outcome=outcome).warning(
                        "External FILLED order for {market_slug}/{outcome} "
                        "but no internal position. Order may have been filled externally.",
                        market_slug=market_slug,
                        outcome=outcome,
                    )

            elif cancelled_orders:
                # External order is CANCELLED
                if has_internal_position:
                    logger.bind(market_slug=market_slug, outcome=outcome).warning(
                        "External CANCELLED order for {market_slug}/{outcome} "
                        "but internal position exists. Position may be stale.",
                        market_slug=market_slug,
                        outcome=outcome,
                    )
                else:
                    logger.bind(market_slug=market_slug, outcome=outcome).debug(
                        "External CANCELLED order for {market_slug}/{outcome} "
                        "(no internal position)",
                        market_slug=market_slug,
                        outcome=outcome,
                    )

            elif open_orders:
                # External order is OPEN (pending)
                logger.bind(market_slug=market_slug, outcome=outcome).debug(
                    "External OPEN order for {market_slug}/{outcome} (pending)",
                    market_slug=market_slug,
                    outcome=outcome,
                )

        # Step 4: Check for internal positions without external orders
        for key in self._positions:
            market_slug, outcome = key
            if key not in external_positions:
                logger.bind(market_slug=market_slug, outcome=outcome).debug(
                    "Internal position {market_slug}/{outcome} has no external orders. "
                    "May be filled externally or order expired.",
                    market_slug=market_slug,
                    outcome=outcome,
                )

        logger.debug(
            "Position sync complete: {internal_count} internal positions, "
            "{external_count} external positions mapped",
            internal_count=len(self._positions),
            external_count=len(external_positions),
        )

    def stop(self) -> None:
        """Stop the position manager."""
        self._running = False

    def get_positions(self) -> dict[tuple[str, Outcome], Position]:
        """Get all current positions (for testing/debugging).

        Returns:
            Dictionary mapping (market_slug, outcome) to Position
        """
        return self._positions.copy()
