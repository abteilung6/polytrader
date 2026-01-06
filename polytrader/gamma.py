"""Gamma API client for Polymarket market data."""

import json

import requests
from pydantic import BaseModel, Field

GAMMA_API_URL = "https://gamma-api.polymarket.com"


class Market(BaseModel):
    id: str
    slug: str
    outcomes: str = Field(..., description="JSON string of outcomes")
    clobTokenIds: str = Field(..., description="JSON string of token IDs")

    def get_outcomes(self) -> list[str]:
        result = json.loads(self.outcomes)
        if not isinstance(result, list):
            raise ValueError("Outcomes must be a list")
        return [str(item) for item in result]

    def get_token_ids(self) -> list[str]:
        result = json.loads(self.clobTokenIds)
        if not isinstance(result, list):
            raise ValueError("Token IDs must be a list")
        return [str(item) for item in result]

    def get_token_id(self, outcome: str) -> str:
        """Get token ID for a specific outcome.

        Accepts both "UP"/"DOWN" and "Up"/"Down" formats and normalizes
        to match Polymarket's actual outcome format.
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

    @staticmethod
    def _normalize_outcome_for_api(outcome: str) -> str:
        """Normalize outcome to match Polymarket API format (Up/Down)."""
        outcome_upper = outcome.upper()
        if outcome_upper == "UP":
            return "Up"
        elif outcome_upper == "DOWN":
            return "Down"
        else:
            return outcome


class GammaClient:
    """Client for Polymarket Gamma API."""

    def __init__(self, base_url: str = GAMMA_API_URL) -> None:
        self.base_url = base_url

    def get_market_by_slug(self, slug: str) -> Market:
        """Get market data by slug from Gamma API.

        See https://docs.polymarket.com/api-reference/markets/get-market-by-slug
        """
        url = f"{self.base_url}/markets/slug/{slug}"

        response = requests.get(url)
        response.raise_for_status()

        data = response.json()
        return Market(**data)
