"""Polymarket CLOB trading adapter.

Per architecture.mdc §H: Adapters contain IO only, no business logic.
This adapter wraps CLOB client and provides normalized trading operations.
"""

import asyncio
from typing import Any, Literal

from py_clob_client.clob_types import (  # type: ignore[import-untyped]
    AssetType,
    BalanceAllowanceParams,
    MarketOrderArgs,
    OpenOrderParams,
    OrderType,
)

from polytrader.adapters.polymarket.market_data import GammaClient
from polytrader.adapters.polymarket.models import VenueError, VenueResponse
from polytrader.clob import IClobClient
from polytrader.logging_config import logger
from polytrader.types import OrderIntentEvent


class ClobVenueAdapter:
    """Adapter for Polymarket CLOB trading API.

    Per architecture.mdc §H: Adapters contain IO only.
    This adapter:
    - Wraps IClobClient and GammaClient
    - Normalizes venue responses
    - Handles retries/backoff (future: Phase 2)
    - Rate limit compliance (future: Phase 2)
    - No business logic

    Attributes:
        clob_client: CLOB client instance
        gamma_client: Gamma client for market lookups
    """

    def __init__(
        self,
        clob_client: IClobClient,
        gamma_client: GammaClient | None = None,
    ) -> None:
        """Initialize CLOB venue adapter.

        Args:
            clob_client: CLOB client instance
            gamma_client: Gamma client for market lookups (defaults to new instance)
        """
        from polytrader.adapters.polymarket.market_data import GammaClient

        self.clob_client = clob_client
        self.gamma_client = gamma_client or GammaClient()

    async def submit_order(
        self,
        client_order_id: str,
        intent: OrderIntentEvent,
    ) -> VenueResponse:
        """Submit order to Polymarket CLOB.

        Per flows.mdc §9: Adapter translates internal command to venue API.

        Args:
            client_order_id: Idempotency key
            intent: Order intent with market/outcome/side/size

        Returns:
            Normalized venue response

        Raises:
            VenueError: If order submission fails
        """
        # Get market info from Gamma
        market = await asyncio.to_thread(self.gamma_client.get_market_by_slug, intent.market_slug)
        token_id = market.get_token_id(intent.outcome)

        # Verify balance for BUY orders
        if intent.side == "BUY":
            await self._verify_balance(intent.size)

        # Place market order
        try:
            response = await asyncio.to_thread(
                self._place_market_order,
                token_id=token_id,
                amount=intent.size,
                side=intent.side,
            )
        except Exception as e:
            # Classify error
            error_type_str = self._classify_error(e)
            # Ensure error_type is a valid Literal
            error_type: Literal["retryable", "fatal"] = (
                "retryable" if error_type_str == "retryable" else "fatal"
            )
            raise VenueError(
                error_type=error_type,
                message=str(e),
                raw_error=e,
            ) from e

        # Normalize response
        venue_order_id = response.get("order_id") or response.get("id", "unknown")
        status = response.get("status") or response.get("state", "unknown")

        return VenueResponse(
            venue_order_id=str(venue_order_id),
            status=str(status),
            raw_response=response,
        )

    async def cancel_order(
        self,
        client_order_id: str,
        venue_order_id: str,
    ) -> VenueResponse:
        """Cancel order on Polymarket CLOB.

        Args:
            client_order_id: Idempotency key
            venue_order_id: Venue-assigned order ID

        Returns:
            Normalized venue response

        Raises:
            VenueError: If cancellation fails
        """
        # TODO: Implement cancel order (Phase 2)
        # For now, return a placeholder response
        raise NotImplementedError("Cancel order not yet implemented")

    async def get_open_orders(
        self,
        market_slug: str | None = None,
        token_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get active orders from Polymarket.

        Args:
            market_slug: Market slug (optional filter)
            token_id: Token ID (optional filter)

        Returns:
            List of active orders from venue
        """
        params = OpenOrderParams(
            market=None,  # TODO: Convert market_slug to condition_id if needed
            asset_id=token_id,
        )
        return await asyncio.to_thread(self.clob_client.get_orders, params)

    async def _verify_balance(self, required_amount: float) -> float:
        """Verify USDC balance is sufficient for the order.

        Args:
            required_amount: Minimum USDC amount required

        Returns:
            Current USDC balance

        Raises:
            ValueError: If balance is insufficient
        """
        balance_params = BalanceAllowanceParams(asset_type=AssetType.COLLATERAL)
        balance_info = await asyncio.to_thread(
            self.clob_client.get_balance_allowance, balance_params
        )

        logger.debug("Raw balance info from API: {info}", info=balance_info)

        balance_str = balance_info.get("balance", "0") or "0"
        balance = float(balance_str)

        logger.info(
            "USDC Balance: {balance} (required: {required})",
            balance=balance,
            required=required_amount,
        )
        logger.debug("Allowance info: {allowance}", allowance=balance_info.get("allowance", "N/A"))
        logger.info("Allowance: Auto-managed (Magic wallet)")

        if balance < required_amount:
            raise ValueError(
                f"Insufficient balance: {balance} USDC < {required_amount} USDC required. "
                "Please deposit USDC to your wallet."
            )

        return balance

    def _place_market_order(
        self,
        token_id: str,
        amount: float,
        side: str,
    ) -> dict[str, Any]:
        """Place a market order on Polymarket (synchronous).

        Args:
            token_id: Token ID for the market outcome
            amount: Dollar amount to spend
            side: Order side (BUY or SELL)

        Returns:
            Order response from the API
        """
        logger.bind(side=side, amount=amount).info(
            "Placing market order: {amount} USDC, side={side}, token_id={token_id}...",
            amount=amount,
            side=side,
            token_id=token_id[:20],
        )
        market_order = MarketOrderArgs(
            token_id=token_id,
            amount=amount,
            side=side,
            order_type=OrderType.FOK,
        )
        signed_order = self.clob_client.create_market_order(market_order)
        order_hash = (
            signed_order.get("hash", "N/A")[:20] if isinstance(signed_order, dict) else "N/A"
        )
        logger.debug("Created signed order (hash: {hash}...)", hash=order_hash)
        response: dict[str, Any] = self.clob_client.post_order(signed_order, OrderType.FOK)

        order_id = response.get("order_id") or response.get("id", "unknown")
        status = response.get("status") or response.get("state", "unknown")
        logger.bind(order_id=order_id, status=status, side=side, amount=amount).info(
            "Order submitted: ID={order_id}, status={status}, side={side}, amount={amount} USDC",
            order_id=order_id,
            status=status,
            side=side,
            amount=amount,
        )
        logger.debug("Full order response: {response}", response=response)
        return response

    def _classify_error(self, error: Exception) -> str:
        """Classify error as retryable or fatal.

        Args:
            error: Exception from venue

        Returns:
            "retryable" or "fatal"
        """
        error_msg = str(error).lower()
        # Network errors are retryable
        if "timeout" in error_msg or "connection" in error_msg:
            return "retryable"
        # Balance/allowance errors are fatal (won't succeed on retry)
        if "balance" in error_msg or "allowance" in error_msg:
            return "fatal"
        # Default to retryable for unknown errors
        return "retryable"
