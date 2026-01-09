"""Position manager for tracking and monitoring trading positions."""

import asyncio
from collections.abc import Callable
from typing import Any, Protocol

from polytrader.clob import ExternalOrder, IClobClientFactory, get_active_orders
from polytrader.events import MARKET_DATA, ORDERS, PROPOSALS, EventBus
from polytrader.gamma import GammaClient
from polytrader.logging_config import logger
from polytrader.types import MarketDataEvent, Order, Outcome, Position, TradeProposal


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
        logger.bind(sync_interval=self.sync_interval).info(
            "Starting PositionManager (sync_interval={sync_interval}s)",
            sync_interval=self.sync_interval,
        )

        # Subscribe to orders and ticks
        orders_queue = self.bus.subscribe(ORDERS)
        market_data_queue = self.bus.subscribe(MARKET_DATA)

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
                        asyncio.create_task(market_data_queue.get()),
                    ],
                    return_when=asyncio.FIRST_COMPLETED,
                )

                # Handle completed tasks
                for task in done:
                    try:
                        result = await task
                        if isinstance(result, Order):
                            await self._handle_order(result)
                        elif isinstance(result, MarketDataEvent):
                            await self._check_target_prices(result)
                    except Exception as e:
                        logger.bind(error_type=type(e).__name__, error=str(e)).exception(
                            "Error processing order or tick: {error_type}: {error}",
                            error_type=type(e).__name__,
                            error=str(e),
                        )

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

            # Calculate position metrics
            position_count = len(self._positions)
            total_size = sum(p.size for p in self._positions.values())

            logger.bind(
                market_slug=order.market_slug,
                outcome=order.outcome,
                size=position.size,
                entry_price=position.entry_price,
                target_price=position.target_price,
                order_id=order_id if order_id != "unknown" else None,
                position_count=position_count,
                total_size=total_size,
            ).info(
                "📈 Position opened: {market_slug}/{outcome} | "
                "size=${size:.2f} | entry={entry_price:.4f} | target={target_price:.4f} | "
                "order_id={order_id} | "
                "total positions: {position_count} (${total_size:.2f})",
                market_slug=order.market_slug,
                outcome=order.outcome,
                size=position.size,
                entry_price=position.entry_price,
                target_price=position.target_price,
                order_id=order_id if order_id != "unknown" else "N/A",
                position_count=position_count,
                total_size=total_size,
            )

        elif order.side == "SELL":
            # Remove position from SELL order
            if key in self._positions:
                position = self._positions.pop(key)

                # Calculate P&L if we have exit price
                exit_price = 0.5  # Default
                if isinstance(order.response, dict):
                    fill_price = order.response.get("fill_price") or order.response.get("price")
                    if fill_price:
                        exit_price = float(fill_price)

                # Calculate profit/loss
                pnl = (exit_price - position.entry_price) * position.size
                pnl_pct = (
                    ((exit_price - position.entry_price) / position.entry_price) * 100
                    if position.entry_price > 0
                    else 0
                )

                # Calculate position duration
                duration_seconds = order.ts - position.entry_time
                duration_minutes = duration_seconds / 60.0

                position_count = len(self._positions)
                total_size = sum(p.size for p in self._positions.values())

                order_id = (
                    order.response.get("order_id") or order.response.get("id", "unknown")
                    if isinstance(order.response, dict)
                    else "unknown"
                )

                logger.bind(
                    market_slug=order.market_slug,
                    outcome=order.outcome,
                    size=position.size,
                    entry_price=position.entry_price,
                    exit_price=exit_price,
                    pnl=pnl,
                    pnl_pct=pnl_pct,
                    duration_seconds=duration_seconds,
                    position_count=position_count,
                    total_size=total_size,
                    order_id=order_id if order_id != "unknown" else None,
                ).info(
                    "📉 Position closed: {market_slug}/{outcome} | "
                    "size=${size:.2f} | entry={entry_price:.4f} | exit={exit_price:.4f} | "
                    "P&L=${pnl:+.2f} ({pnl_pct:+.1f}%) | duration={duration_minutes:.1f}m | "
                    "order_id={order_id} | "
                    "remaining positions: {position_count} (${total_size:.2f})",
                    market_slug=order.market_slug,
                    outcome=order.outcome,
                    size=position.size,
                    entry_price=position.entry_price,
                    exit_price=exit_price,
                    pnl=pnl,
                    pnl_pct=pnl_pct,
                    duration_minutes=duration_minutes,
                    order_id=order_id if order_id != "unknown" else "N/A",
                    position_count=position_count,
                    total_size=total_size,
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

    async def _check_target_prices(self, event: MarketDataEvent) -> None:
        """Check if any positions have reached their target price.

        Generates SELL proposals when target prices are reached.
        """
        key = (event.market_slug, event.outcome)

        if key not in self._positions:
            # No position for this market/outcome - nothing to sell
            logger.bind(
                market_slug=event.market_slug,
                outcome=event.outcome,
            ).debug(
                "No position to check: {market_slug}/{outcome}",
                market_slug=event.market_slug,
                outcome=event.outcome,
            )
            return

        position = self._positions[key]
        mid_price = event.mid

        # Check if target price is reached (for BUY positions, sell when price >= target)
        if mid_price >= position.target_price:
            logger.bind(
                market_slug=event.market_slug,
                outcome=event.outcome,
                current_price=mid_price,
                target_price=position.target_price,
            ).info(
                "Target price reached: {current_price:.4f} >= {target_price:.4f} "
                "for {market_slug}/{outcome}",
                current_price=mid_price,
                target_price=position.target_price,
                market_slug=event.market_slug,
                outcome=event.outcome,
            )

            # Generate SELL proposal
            proposal = TradeProposal(
                ts=event.ts_mono,  # Use monotonic timestamp from event
                market_slug=event.market_slug,
                outcome=event.outcome,
                side="SELL",
                target_price=position.target_price,
                limit_price=event.best_bid,
                size=position.size,
                reason=(
                    f"Target price reached: {mid_price:.4f} >= {position.target_price:.4f} "
                    f"(entry: {position.entry_price:.4f})"
                ),
            )

            await self.bus.publish(PROPOSALS, proposal)

            logger.bind(
                market_slug=event.market_slug,
                outcome=event.outcome,
                price=mid_price,
            ).info(
                "Published SELL proposal: target reached at {price:.4f}",
                price=mid_price,
            )
        else:
            # Price hasn't reached target yet - log why we're not selling
            price_diff = position.target_price - mid_price
            price_pct = (
                (price_diff / position.target_price) * 100 if position.target_price > 0 else 0
            )
            profit_pct = (
                ((mid_price - position.entry_price) / position.entry_price) * 100
                if position.entry_price > 0
                else 0
            )

            logger.bind(
                market_slug=event.market_slug,
                outcome=event.outcome,
                current_price=mid_price,
                target_price=position.target_price,
                entry_price=position.entry_price,
                size=position.size,
                price_diff=price_diff,
                price_pct=price_pct,
                profit_pct=profit_pct,
            ).info(
                "⏸️  Not selling {market_slug}/{outcome}: "
                "current={current_price:.4f} < target={target_price:.4f} "
                "(need +{price_diff:.4f}, {price_pct:.1f}% more) | "
                "entry={entry_price:.4f} | profit={profit_pct:+.1f}% | size=${size:.2f}",
                market_slug=event.market_slug,
                outcome=event.outcome,
                current_price=mid_price,
                target_price=position.target_price,
                entry_price=position.entry_price,
                size=position.size,
                price_diff=price_diff,
                price_pct=price_pct,
                profit_pct=profit_pct,
            )

    async def _periodic_sync(self) -> None:
        """Periodically sync with external API and log position status."""
        while self._running:
            await asyncio.sleep(self.sync_interval)
            try:
                # Log position status before sync
                await self._log_position_status()
                await self._sync_with_external()
            except Exception:
                logger.exception("Error in periodic sync")

    async def _log_position_status(self) -> None:
        """Log current position status for observability."""
        if not self._positions:
            logger.debug("No active positions")
            return

        total_size = sum(p.size for p in self._positions.values())
        import time

        now = time.time()

        # Calculate aggregate metrics
        positions_summary = []

        for key, position in self._positions.items():
            market_slug, outcome = key
            # Estimate current value (would need current price, using entry as placeholder)
            # In a real system, you'd fetch current market price
            duration_minutes = (now - position.entry_time) / 60.0

            positions_summary.append(
                {
                    "market_slug": market_slug,
                    "outcome": outcome,
                    "size": position.size,
                    "entry_price": position.entry_price,
                    "target_price": position.target_price,
                    "duration_minutes": duration_minutes,
                }
            )

        logger.bind(
            position_count=len(self._positions),
            total_size=total_size,
        ).info(
            "📊 Position status: {position_count} active positions, total size=${total_size:.2f}",
            position_count=len(self._positions),
            total_size=total_size,
        )

        # Log each position (at debug level to avoid spam)
        for pos_info in positions_summary:
            logger.bind(
                market_slug=pos_info["market_slug"],
                outcome=pos_info["outcome"],
                size=pos_info["size"],
                entry_price=pos_info["entry_price"],
                target_price=pos_info["target_price"],
                duration_minutes=pos_info["duration_minutes"],
            ).debug(
                "  Position: {market_slug}/{outcome} | "
                "size=${size:.2f} | entry={entry_price:.4f} | target={target_price:.4f} | "
                "duration={duration_minutes:.1f}m",
                market_slug=pos_info["market_slug"],
                outcome=pos_info["outcome"],
                size=pos_info["size"],
                entry_price=pos_info["entry_price"],
                target_price=pos_info["target_price"],
                duration_minutes=pos_info["duration_minutes"],
            )

    async def _sync_with_external(self) -> None:
        """Sync internal positions with external API state."""
        internal_count_before = len(self._positions)
        logger.bind(internal_count=internal_count_before).debug(
            "Syncing positions with external API (internal: {internal_count})",
            internal_count=internal_count_before,
        )

        try:
            client = self.clob_client_factory()

            # Get all active orders from external API
            external_orders = await asyncio.to_thread(lambda: get_active_orders(client))

            logger.bind(external_count=len(external_orders)).debug(
                "Retrieved {external_count} external orders",
                external_count=len(external_orders),
            )

            # Reconcile with internal positions
            await self._reconcile_positions(external_orders)

            internal_count_after = len(self._positions)
            if internal_count_before != internal_count_after:
                logger.bind(
                    before=internal_count_before,
                    after=internal_count_after,
                    delta=internal_count_after - internal_count_before,
                ).info(
                    "Position sync complete: {before} → {after} positions (Δ{delta:+d})",
                    before=internal_count_before,
                    after=internal_count_after,
                    delta=internal_count_after - internal_count_before,
                )

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

    async def _lookup_token_id(self, token_id: str) -> tuple[str, Outcome] | None:
        """Look up market_slug and outcome from token_id via Gamma API.

        This is used for unknown tokens that aren't in our cache.
        The result is cached for future lookups.

        Args:
            token_id: Token ID to look up

        Returns:
            Tuple of (market_slug, outcome) if found, None otherwise
        """
        # Try to find the market by iterating through known markets
        # This is a fallback - in practice, we should have most tokens cached
        # For now, we'll return None and log a warning
        # In a production system, you might want to maintain a reverse index
        # or query Gamma API for token metadata
        logger.bind(token_id=token_id).warning(
            "Token ID {token_id} not in cache and lookup not implemented. "
            "Consider caching token_id when positions are created.",
            token_id=token_id,
        )
        return None

    def _create_position_from_external_order(
        self, external_order: ExternalOrder, market_slug: str, outcome: Outcome
    ) -> Position:
        """Create a Position from an external order.

        Used when we discover an externally filled order that we don't have
        an internal position for. Uses reasonable defaults for missing data.

        Args:
            external_order: External order that was filled
            market_slug: Market slug (from token lookup)
            outcome: Outcome (from token lookup)

        Returns:
            Position with estimated values
        """
        import time

        # Use defaults for missing information
        # Entry price: assume 0.5 (mid-market) if not available
        entry_price = 0.5
        # Target price: default to 0.5 (will be updated if we get better info)
        target_price = 0.5
        # Entry time: use current time as estimate
        entry_time = time.time()

        return Position(
            market_slug=market_slug,
            outcome=outcome,
            size=external_order.size,
            target_price=target_price,
            entry_price=entry_price,
            entry_time=entry_time,
            order_id=external_order.order_id if external_order.order_id != "unknown" else None,
        )

    def _remove_position(self, key: tuple[str, Outcome], reason: str) -> None:
        """Remove a position and clean up related mappings.

        Args:
            key: Position key (market_slug, outcome)
            reason: Reason for removal (for logging)
        """
        if key not in self._positions:
            return

        position = self._positions.pop(key)
        logger.bind(
            market_slug=position.market_slug,
            outcome=position.outcome,
            reason=reason,
        ).info(
            "Removed position {market_slug}/{outcome}: {reason}",
            market_slug=position.market_slug,
            outcome=position.outcome,
            reason=reason,
        )

        # Clean up order_id mapping
        if position.order_id:
            self._order_id_to_position.pop(position.order_id, None)

    async def _reconcile_positions(self, external_orders: list[dict[str, Any]]) -> None:
        """Reconcile internal positions with external orders.

        Automatically synchronizes internal positions with external API state:
        - Removes positions when external orders are CANCELLED
        - Creates positions for externally filled BUY orders
        - Attempts to look up unknown token_ids via Gamma API

        Args:
            external_orders: List of order dictionaries from external API
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
        unknown_tokens: list[ExternalOrder] = []

        for parsed in parsed_orders:
            token_id = parsed.token_id
            market_info = self._get_market_from_token(token_id)

            if market_info:
                market_slug, outcome = market_info
                key = (market_slug, outcome)
                external_positions.setdefault(key, []).append(parsed)
            else:
                # Try to look up via Gamma API
                lookup_result = await self._lookup_token_id(token_id)
                if lookup_result:
                    market_slug, outcome = lookup_result
                    key = (market_slug, outcome)
                    external_positions.setdefault(key, []).append(parsed)
                    # Cache the result
                    self._token_to_market[token_id] = lookup_result
                else:
                    unknown_tokens.append(parsed)

        if unknown_tokens:
            logger.debug(
                "Found {count} external orders with unknown token_ids "
                "(not in cache and lookup failed)",
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
                    # Create position for externally filled order (BUY only)
                    buy_orders = [o for o in filled_orders if o.side == "BUY"]
                    if buy_orders:
                        # Use the first BUY order to create position
                        external_order = buy_orders[0]
                        position = self._create_position_from_external_order(
                            external_order, market_slug, outcome
                        )
                        self._positions[key] = position
                        if external_order.order_id != "unknown":
                            self._order_id_to_position[external_order.order_id] = key

                        position_count = len(self._positions)
                        total_size = sum(p.size for p in self._positions.values())

                        logger.bind(
                            market_slug=market_slug,
                            outcome=outcome,
                            size=position.size,
                            order_id=external_order.order_id
                            if external_order.order_id != "unknown"
                            else None,
                            position_count=position_count,
                            total_size=total_size,
                        ).info(
                            "🔍 Discovered external position: {market_slug}/{outcome} | "
                            "size=${size:.2f} | order_id={order_id} | "
                            "total positions: {position_count} (${total_size:.2f})",
                            market_slug=market_slug,
                            outcome=outcome,
                            size=position.size,
                            order_id=external_order.order_id
                            if external_order.order_id != "unknown"
                            else "N/A",
                            position_count=position_count,
                            total_size=total_size,
                        )
                    else:
                        logger.bind(market_slug=market_slug, outcome=outcome).debug(
                            "External FILLED SELL order for {market_slug}/{outcome} "
                            "(no internal position, skipping)",
                            market_slug=market_slug,
                            outcome=outcome,
                        )

            elif cancelled_orders:
                # External order is CANCELLED
                if has_internal_position:
                    # Remove stale position - order was cancelled externally
                    cancelled_order_ids = [
                        o.order_id for o in cancelled_orders if o.order_id != "unknown"
                    ]
                    reason = (
                        f"External order CANCELLED (order_ids: {', '.join(cancelled_order_ids)})"
                        if cancelled_order_ids
                        else "External order CANCELLED"
                    )
                    self._remove_position(key, reason)
                else:
                    logger.bind(market_slug=market_slug, outcome=outcome).debug(
                        "External CANCELLED order for {market_slug}/{outcome} "
                        "(no internal position, ignoring)",
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

        # Log summary with more details
        total_size = sum(p.size for p in self._positions.values())
        logger.bind(
            internal_count=len(self._positions),
            external_count=len(external_positions),
            total_size=total_size,
            unknown_tokens=len(unknown_tokens),
        ).debug(
            "Position reconciliation: {internal_count} internal, {external_count} external mapped, "
            "{unknown_tokens} unknown tokens, total size=${total_size:.2f}",
            internal_count=len(self._positions),
            external_count=len(external_positions),
            unknown_tokens=len(unknown_tokens),
            total_size=total_size,
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
