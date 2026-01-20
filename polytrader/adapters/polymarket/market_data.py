"""Polymarket Gamma API client for market data.

Per architecture.mdc §H: Adapters contain IO only, no business logic.
This adapter provides market data lookup (market info, token IDs).
"""

import json

import requests
from pydantic import BaseModel, Field

GAMMA_API_URL = "https://gamma-api.polymarket.com"


class Market(BaseModel):
    """Market data model from Gamma API.

    Attributes:
        id: Market ID
        slug: Market slug
        outcomes: JSON string of outcomes
        clobTokenIds: JSON string of token IDs
        startDate: Market start date (ISO 8601 UTC timestamp, optional)
        endDate: Market end date (ISO 8601 UTC timestamp)
        active: Whether market is active
        closed: Whether market is closed/resolved
        acceptingOrders: Whether market accepts orders (has orderbook)
    """

    id: str
    slug: str
    outcomes: str = Field(..., description="JSON string of outcomes")
    clobTokenIds: str = Field(..., description="JSON string of token IDs")
    startDate: str | None = Field(
        default=None, description="Market start date (ISO 8601 UTC timestamp)"
    )
    endDate: str | None = Field(
        default=None, description="Market end date (ISO 8601 UTC timestamp)"
    )
    active: bool = Field(default=True, description="Whether market is active")
    closed: bool = Field(default=False, description="Whether market is closed/resolved")
    acceptingOrders: bool = Field(
        default=True, description="Whether market accepts orders (has orderbook)"
    )

    def get_outcomes(self) -> list[str]:
        """Parse outcomes from JSON string.

        Returns:
            List of outcome strings
        """
        result = json.loads(self.outcomes)
        if not isinstance(result, list):
            raise ValueError("Outcomes must be a list")
        return [str(item) for item in result]

    def get_token_ids(self) -> list[str]:
        """Parse token IDs from JSON string.

        Returns:
            List of token ID strings
        """
        result = json.loads(self.clobTokenIds)
        if not isinstance(result, list):
            raise ValueError("Token IDs must be a list")
        return [str(item) for item in result]

    def get_token_id(self, outcome: str) -> str:
        """Get token ID for a specific outcome.

        Accepts both "UP"/"DOWN" and "Up"/"Down" formats and normalizes
        to match Polymarket's actual outcome format.

        Args:
            outcome: Outcome name (UP, DOWN, Up, Down)

        Returns:
            Token ID for the outcome

        Raises:
            ValueError: If outcome not found
        """
        outcomes = self.get_outcomes()
        token_ids = self.get_token_ids()

        if len(outcomes) != len(token_ids):
            raise ValueError("Mismatch between outcomes and token IDs")

        outcome_normalized = self._normalize_outcome_for_api(outcome)

        try:
            outcome_index = outcomes.index(outcome_normalized)
            return token_ids[outcome_index]
        except ValueError as err:
            available = ", ".join(outcomes)
            raise ValueError(f"Outcome '{outcome}' not found. Available: {available}") from err

    def is_expired(self) -> bool:
        """Check if market has expired based on endDate.

        Returns:
            True if market endDate has passed, False otherwise
        """
        if self.endDate is None:
            return False  # Can't determine if expired without endDate

        from datetime import UTC, datetime

        try:
            end_time = datetime.fromisoformat(self.endDate.replace("Z", "+00:00"))
            now = datetime.now(UTC)
            return end_time < now
        except (ValueError, AttributeError):
            # If parsing fails, assume not expired (conservative)
            return False

    def is_resolved(self) -> bool:
        """Check if market is resolved/closed.

        Returns:
            True if market is closed/resolved, False otherwise
        """
        return self.closed

    def is_tradeable(self) -> bool:
        """Check if market is tradeable (active, accepting orders, not closed).

        Returns:
            True if market can be traded, False otherwise
        """
        return self.active and self.acceptingOrders and not self.closed

    @staticmethod
    def _normalize_outcome_for_api(outcome: str) -> str:
        """Normalize outcome to match Polymarket API format (Up/Down).

        Args:
            outcome: Outcome string (UP, DOWN, Up, Down)

        Returns:
            Normalized outcome (Up or Down)
        """
        outcome_upper = outcome.upper()
        if outcome_upper == "UP":
            return "Up"
        elif outcome_upper == "DOWN":
            return "Down"
        else:
            return outcome


class GammaClient:
    """Client for Polymarket Gamma API.

    Per architecture.mdc §H: Adapters contain IO only.
    This client provides market data lookup functionality.

    Attributes:
        base_url: Base URL for Gamma API
    """

    def __init__(
        self,
        base_url: str = GAMMA_API_URL,
    ) -> None:
        """Initialize Gamma client.

        Args:
            base_url: Base URL for Gamma API (defaults to production)
        """
        self.base_url = base_url

    def get_market_by_slug(self, slug: str) -> Market:
        """Get market data by slug from Gamma API.

        See https://docs.polymarket.com/api-reference/markets/get-market-by-slug

        The API response includes startDate and endDate fields directly.

        Args:
            slug: Market slug (e.g., "btc-updown-15m-1768766400")

        Returns:
            Market data model with startDate and endDate from API

        Raises:
            requests.RequestException: If API request fails
        """
        url = f"{self.base_url}/markets/slug/{slug}"

        response = requests.get(url)
        response.raise_for_status()

        data = response.json()
        return Market(**data)
