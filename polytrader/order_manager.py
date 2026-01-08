import asyncio
import logging
import time
from collections.abc import Callable
from typing import Any, Protocol

from polytrader.clob import IClobClientFactory, place_market_order, verify_usdc_balance
from polytrader.events import ORDERS, PROPOSALS, EventBus
from polytrader.gamma import GammaClient
from polytrader.types import Order, Outcome, TradeProposal

logger = logging.getLogger(__name__)


class IOrderManager(Protocol):
    """Protocol for order manager components."""

    async def run(self) -> None:
        """Start the order manager."""
        ...

    def stop(self) -> None:
        """Stop the order manager."""
        ...


def create_order_manager_factory(
    bus: EventBus,
    clob_client_factory: IClobClientFactory,
    gamma_client: GammaClient | None = None,
    max_trades_per_market: int = 1,
) -> Callable[[], IOrderManager]:
    """Create a factory function for IOrderManager.

    Args:
        bus: Event bus for publishing orders
        clob_client_factory: Factory for creating CLOB clients
        gamma_client: Gamma API client (optional)
        max_trades_per_market: Maximum trades per market/outcome

    Returns:
        Factory function that returns order manager
    """

    def factory() -> IOrderManager:
        return OrderManager(
            bus=bus,
            clob_client_factory=clob_client_factory,
            gamma_client=gamma_client,
            max_trades_per_market=max_trades_per_market,
        )

    return factory


class OrderManager(IOrderManager):
    def __init__(
        self,
        bus: EventBus,
        clob_client_factory: IClobClientFactory,
        gamma_client: GammaClient | None = None,
        max_trades_per_market: int = 1,
    ) -> None:
        self.bus = bus
        self.clob_client_factory = clob_client_factory
        self.gamma_client = gamma_client or GammaClient()
        self.max_trades_per_market = max_trades_per_market
        self._executed_trades: set[tuple[str, Outcome]] = set()
        self._owned_tokens: set[tuple[str, Outcome]] = set()
        self._running = False

    async def run(self) -> None:
        self._running = True
        proposal_queue = self.bus.subscribe(PROPOSALS)

        try:
            while self._running:
                proposal = await proposal_queue.get()
                await self._process_proposal(proposal)
        except Exception as e:
            logger.error(f"OrderManager error: {e}", exc_info=True)
            raise
        finally:
            self._running = False

    async def _process_proposal(self, proposal: TradeProposal) -> None:
        if not self._is_proposal_valid(proposal):
            return

        if proposal.side == "SELL" and not self._has_tokens(proposal.market_slug, proposal.outcome):
            logger.info(
                f"Skipping SELL proposal: no tokens owned for "
                f"{proposal.market_slug}/{proposal.outcome}. "
                "Cannot sell tokens you don't own."
            )
            return

        if self._has_traded(proposal.market_slug, proposal.outcome):
            logger.info(
                f"Skipping proposal: already traded {proposal.market_slug}/{proposal.outcome}. "
                f"Limit: {self.max_trades_per_market} trade(s) per market"
            )
            return

        try:
            logger.info(
                f"Processing {proposal.side} proposal for "
                f"{proposal.market_slug}/{proposal.outcome}: {proposal.reason}"
            )

            response = await self._execute_order(proposal)
            self._executed_trades.add((proposal.market_slug, proposal.outcome))

            if proposal.side == "BUY":
                self._owned_tokens.add((proposal.market_slug, proposal.outcome))
                logger.debug(f"Added {proposal.market_slug}/{proposal.outcome} to owned tokens")
            elif proposal.side == "SELL":
                self._owned_tokens.discard((proposal.market_slug, proposal.outcome))
                logger.debug(f"Removed {proposal.market_slug}/{proposal.outcome} from owned tokens")

            order = Order(
                ts=time.time(),
                market_slug=proposal.market_slug,
                outcome=proposal.outcome,
                side=proposal.side,
                size=proposal.size,
                proposal_reason=proposal.reason,
                response=response,
            )
            await self.bus.publish(ORDERS, order)

            order_id = (
                response.get("order_id") or response.get("id", "unknown")
                if isinstance(response, dict)
                else "unknown"
            )
            logger.info(
                f"✅ Successfully executed {proposal.side} order (ID: {order_id}) for "
                f"{proposal.market_slug}/{proposal.outcome}: {proposal.reason}"
            )
        except Exception as e:
            error_msg = str(e)
            if "not enough balance" in error_msg.lower() or "allowance" in error_msg.lower():
                if proposal.side == "SELL":
                    logger.warning(
                        f"Cannot sell {proposal.market_slug}/{proposal.outcome}: "
                        f"insufficient token balance. Error: {error_msg}"
                    )
                else:
                    logger.error(
                        f"Balance/allowance error executing {proposal.side} order for "
                        f"{proposal.market_slug}/{proposal.outcome}: {error_msg}. "
                        "Please check your USDC balance and allowance."
                    )
            else:
                logger.error(f"Failed to execute order: {e}", exc_info=True)

    def _is_proposal_valid(self, proposal: TradeProposal) -> bool:
        current_time = time.time()
        age = current_time - proposal.ts

        if age > proposal.ttl_s:
            logger.debug(
                f"Proposal expired: age {age:.2f}s > TTL {proposal.ttl_s}s. "
                f"Market: {proposal.market_slug}, Outcome: {proposal.outcome}"
            )
            return False

        if proposal.size <= 0:
            logger.warning(f"Invalid proposal size: {proposal.size}. Skipping.")
            return False

        return True

    def _has_traded(self, market_slug: str, outcome: Outcome) -> bool:
        return (market_slug, outcome) in self._executed_trades

    def _has_tokens(self, market_slug: str, outcome: Outcome) -> bool:
        """Check if we own tokens for this market/outcome."""
        return (market_slug, outcome) in self._owned_tokens

    async def _execute_order(self, proposal: TradeProposal) -> dict[str, Any]:
        market = await asyncio.to_thread(self.gamma_client.get_market_by_slug, proposal.market_slug)
        token_id = market.get_token_id(proposal.outcome)

        client = self.clob_client_factory()

        if proposal.side == "BUY":
            await asyncio.to_thread(
                lambda: verify_usdc_balance(client, required_amount=proposal.size)
            )

        response = await asyncio.to_thread(
            lambda: place_market_order(
                client,
                token_id=token_id,
                amount=proposal.size,
                side=proposal.side,
            )
        )
        return response

    def stop(self) -> None:
        self._running = False

    def reset_trades(self) -> None:
        """Reset executed trades tracking. Useful for testing."""
        self._executed_trades.clear()
        self._owned_tokens.clear()

    def reset_owned_tokens(self) -> None:
        """Reset owned tokens tracking. Useful for testing."""
        self._owned_tokens.clear()
