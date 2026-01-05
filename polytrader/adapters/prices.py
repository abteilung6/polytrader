from pydantic import BaseModel, Field


class TokenPrices(BaseModel):
    """Price data for a single token.

    Attributes:
        BUY: Best ask price (what sellers ask, as string)
        SELL: Best bid price (what buyers offer, as string)
    """

    BUY: str = Field(..., description="Best ask price (what sellers ask)")
    SELL: str = Field(..., description="Best bid price (what buyers offer)")

    def get_best_bid(self) -> float:
        """Get best bid price as float.

        Returns:
            Best bid price (from SELL side)
        """
        return float(self.SELL)

    def get_best_ask(self) -> float:
        """Get best ask price as float.

        Returns:
            Best ask price (from BUY side)
        """
        return float(self.BUY)


class PricesResponse(BaseModel):
    """Response from POST /prices endpoint.

    The response is a dictionary mapping token_id to TokenPrices.
    This model validates the structure and provides type safety.
    """

    def __init__(self, data: dict) -> None:
        """Initialize from raw API response.

        Args:
            data: Raw response dict from API: {token_id: {"BUY": "...", "SELL": "..."}}
        """
        for token_id, prices in data.items():
            if not isinstance(prices, dict):
                raise ValueError(f"Invalid prices format for token_id {token_id}")
            TokenPrices(**prices)

        super().__init__()
        self._data = data

    def get_token_prices(self, token_id: str) -> TokenPrices | None:
        """Get prices for a specific token.

        Args:
            token_id: Token ID to look up

        Returns:
            TokenPrices if found, None otherwise
        """
        prices_dict = self._data.get(token_id)
        if prices_dict is None:
            return None
        return TokenPrices(**prices_dict)


def unmarshall_token_prices(response: dict, token_id: str) -> TokenPrices | None:
    """Extract and validate prices for a token from API response.

    Args:
        response: Raw API response dict: {token_id: {"BUY": "...", "SELL": "..."}}
        token_id: Token ID to extract prices for

    Returns:
        TokenPrices if found and valid, None otherwise
    """
    prices_response = PricesResponse(response)
    return prices_response.get_token_prices(token_id)
