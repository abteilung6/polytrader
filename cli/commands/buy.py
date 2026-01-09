"""Buy command handler."""

import argparse

from py_clob_client.client import ClobClient  # type: ignore[import-untyped]
from py_clob_client.order_builder.constants import BUY  # type: ignore[import-untyped]

from polytrader.clob import place_market_order, verify_usdc_balance
from polytrader.config import CHAIN_ID, CLOB_API_URL, PolymarketSecrets
from polytrader.gamma import GammaClient
from cli.utils import resolve_market_slug


def buy_mode(args: argparse.Namespace) -> None:
    """Place a buy order on Polymarket."""
    secrets = PolymarketSecrets()
    print("Secrets loaded successfully!")

    # Resolve market slug
    market_slug, _ = resolve_market_slug(args.asset, args.time_period, args.market)
    print(f"Resolved market slug: {market_slug}")

    gamma = GammaClient()
    market = gamma.get_market_by_slug(market_slug)
    # Default to "Up" outcome
    outcome = "Up"
    token_id = market.get_token_id(outcome)
    print(f"Token ID for '{outcome}': {token_id}")

    client = ClobClient(
        host=CLOB_API_URL,
        key=secrets.private_key.get_secret_value(),
        chain_id=CHAIN_ID,
        signature_type=secrets.signature_type,
        funder=secrets.funder,
    )

    creds = client.create_or_derive_api_creds()
    client.set_api_creds(creds)

    verify_usdc_balance(client, required_amount=args.amount)

    response = place_market_order(client, token_id=token_id, amount=args.amount, side=BUY)
    
    # Safely print response without exposing sensitive data
    success = response.get("success", False)
    order_id = response.get("orderID", "")
    status = response.get("status", "")
    taking_amount = response.get("takingAmount", "")
    making_amount = response.get("makingAmount", "")
    
    print(f"Order placed! Success: {success}")
    if order_id:
        print(f"Order ID: {order_id}")
    if status:
        print(f"Status: {status}")
    if taking_amount:
        print(f"Shares received: {taking_amount}")
    if making_amount:
        print(f"USDC spent: {making_amount}")
    
    if not success:
        error_msg = response.get("errorMsg", "")
        if error_msg:
            print(f"Error: {error_msg}")

