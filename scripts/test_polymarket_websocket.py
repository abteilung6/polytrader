#!/usr/bin/env python3
"""Discovery script to test Polymarket WebSocket connection.

This script verifies:
1. WebSocket connection to Polymarket
2. Authentication flow
3. User channel subscription
4. Message formats and field names
5. Event types received

Usage:
    python scripts/test_polymarket_websocket.py

Requirements:
    - PRIVATE_KEY environment variable set
    - Optional: FUNDER, SIGNATURE_TYPE environment variables

Note: This is a discovery/testing script, not part of the production codebase.
It's useful for:
- Verifying WebSocket connectivity
- Capturing actual message formats for schema validation
- Debugging connection issues
- Testing authentication flow

Keep this script for future debugging and discovery needs.
"""

import asyncio
import json
import os
import sys
from datetime import UTC, datetime

import websockets
from loguru import logger

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from polytrader.adapters.polymarket.user_stream import (
    WS_PING,
    WS_PONG,
    WS_USER_URL,
)
from polytrader.clob import create_clob_client_factory
from polytrader.config import PolymarketSecrets

# Configure logging
logger.remove()
logger.add(
    sys.stderr,
    format=(
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | <level>{message}</level>"
    ),
    level="INFO",
)


async def test_websocket_connection() -> None:
    """Test WebSocket connection to Polymarket."""
    # Load secrets
    try:
        secrets = PolymarketSecrets()
    except Exception as e:
        logger.error(f"Failed to load secrets: {e}")
        logger.info("Make sure PRIVATE_KEY is set in .env file or environment")
        sys.exit(1)

    # Create CLOB client factory
    clob_client_factory = create_clob_client_factory(secrets)
    clob_client = clob_client_factory()

    # Get API credentials
    try:
        api_creds = clob_client.create_or_derive_api_creds()
        logger.info("Retrieved API credentials from CLOB client")
        logger.debug(f"API creds type: {type(api_creds)}")
    except Exception as e:
        logger.error(f"Failed to get API credentials: {e}")
        sys.exit(1)

    # Try to extract apiKey, secret, and passphrase
    # ApiCreds might be a dict, dataclass, or object with attributes
    if isinstance(api_creds, dict):
        api_key = api_creds.get("apiKey") or api_creds.get("api_key")
        api_secret = (
            api_creds.get("secret") or api_creds.get("apiSecret") or api_creds.get("api_secret")
        )
        api_passphrase = api_creds.get("passphrase") or api_creds.get("api_passphrase")
    else:
        # Try as attributes (camelCase or snake_case)
        api_key = getattr(api_creds, "apiKey", None) or getattr(api_creds, "api_key", None)
        api_secret = (
            getattr(api_creds, "secret", None)
            or getattr(api_creds, "apiSecret", None)
            or getattr(api_creds, "api_secret", None)
        )
        api_passphrase = getattr(api_creds, "passphrase", None) or getattr(
            api_creds, "api_passphrase", None
        )
        # If still not found, try to convert to dict if possible
        if not api_key or not api_secret:
            try:
                if hasattr(api_creds, "__dict__"):
                    api_key = api_creds.__dict__.get("apiKey") or api_creds.__dict__.get("api_key")
                    api_secret = (
                        api_creds.__dict__.get("secret")
                        or api_creds.__dict__.get("apiSecret")
                        or api_creds.__dict__.get("api_secret")
                    )
                    api_passphrase = api_creds.__dict__.get("passphrase") or api_creds.__dict__.get(
                        "api_passphrase"
                    )
            except Exception:
                pass

    if not api_key or not api_secret:
        logger.error("API credentials missing apiKey or secret")
        logger.debug(f"API creds type: {type(api_creds)}")
        if isinstance(api_creds, dict):
            logger.debug(f"Available keys: {list(api_creds.keys())}")
        else:
            logger.debug(f"Available attributes: {dir(api_creds)}")
        sys.exit(1)

    api_key_preview = f"{api_key[:10]}... (truncated)"
    api_secret_preview = f"{api_secret[:10]}... (truncated)"
    logger.info(f"API Key: {api_key_preview}")
    logger.info(f"API Secret: {api_secret_preview}")
    if api_passphrase:
        logger.info(f"API Passphrase: {'*' * len(api_passphrase)} (hidden)")

    # Connect to WebSocket
    logger.info(f"Connecting to {WS_USER_URL}...")
    try:
        async with websockets.connect(WS_USER_URL) as ws:
            logger.info("✓ WebSocket connected")

            # Subscribe to user channel with authentication
            # Per Polymarket API: send subscription message with auth on connection
            logger.info("Subscribing to user channel with authentication...")
            subscribe_message = {
                "type": "user",
                "markets": [],  # Empty array subscribes to all markets
                "auth": {
                    "apiKey": api_key,
                    "secret": api_secret,
                    "passphrase": api_passphrase or "",  # Passphrase may be optional
                },
            }
            logger.debug(f"Subscribe message: {json.dumps(subscribe_message, indent=2)}")
            await ws.send(json.dumps(subscribe_message))

            logger.info("✓ Subscribed to user channel")

            # Start ping task to keep connection alive
            async def ping_loop():
                try:
                    while True:
                        await asyncio.sleep(10.0)  # Send ping every 10 seconds
                        await ws.send(WS_PING)
                        logger.debug("Sent PING to keep connection alive")
                except asyncio.CancelledError:
                    pass

            ping_task = asyncio.create_task(ping_loop())
            logger.info("")
            logger.info("=" * 80)
            logger.info("Listening for user stream messages...")
            logger.info("(Press Ctrl+C to stop)")
            logger.info("=" * 80)
            logger.info("")

            # Step 3: Listen for messages
            message_count = 0
            try:
                async for raw_message in ws:
                    message_count += 1
                    timestamp = datetime.now(UTC).isoformat()

                    # Handle plain text PING/PONG messages (not JSON)
                    message_stripped = raw_message.strip()
                    if message_stripped == WS_PING:
                        logger.info(f"[{timestamp}] Received PING, responding with PONG")
                        await ws.send(WS_PONG)
                        continue
                    elif message_stripped == WS_PONG:
                        logger.debug(f"[{timestamp}] Received PONG (response to our PING)")
                        continue

                    # Convert bytes to str if needed
                    message_str = (
                        raw_message if isinstance(raw_message, str) else raw_message.decode("utf-8")
                    )

                    # Print raw message for debugging
                    logger.info(f"[{timestamp}] Raw message received:")
                    logger.info(f"  Length: {len(message_str)} bytes")
                    logger.info(f"  First 200 chars: {message_str[:200]}")
                    logger.info(f"  Repr: {repr(message_str)}")

                    try:
                        message = json.loads(message_str)
                    except json.JSONDecodeError as e:
                        logger.warning(f"[{timestamp}] Failed to parse message as JSON: {e}")
                        logger.warning(f"  Raw message (first 500 chars): {message_str[:500]}")
                        logger.warning(f"  Raw message (repr): {repr(message_str)}")
                        continue

                    # Log message details
                    msg_type = message.get("type", "unknown")
                    channel = message.get("channel", "unknown")

                    logger.info(f"[{timestamp}] Message #{message_count}")
                    logger.info(f"  Type: {msg_type}")
                    logger.info(f"  Channel: {channel}")
                    logger.info("  Full message:")
                    logger.info(json.dumps(message, indent=4))

                    # Analyze message structure
                    if channel == "user":
                        logger.info("  → This is a user channel message")
                        if msg_type in ("order", "order_update"):
                            logger.info("  → Order update (ack/reject)")
                            logger.info(f"    - orderId: {message.get('orderId')}")
                            logger.info(f"    - clientOrderId: {message.get('clientOrderId')}")
                            logger.info(f"    - status: {message.get('status')}")
                            logger.info(f"    - reason: {message.get('reason')}")
                        elif msg_type in ("fill", "fill_update"):
                            logger.info("  → Fill event")
                            logger.info(f"    - fillId: {message.get('fillId')}")
                            logger.info(f"    - orderId: {message.get('orderId')}")
                            logger.info(f"    - size: {message.get('size')}")
                            logger.info(f"    - price: {message.get('price')}")
                            logger.info(f"    - fee: {message.get('fee')}")
                        elif msg_type in ("cancel", "cancel_update"):
                            logger.info("  → Cancel event")
                            logger.info(f"    - orderId: {message.get('orderId')}")
                            logger.info(f"    - clientOrderId: {message.get('clientOrderId')}")
                        elif msg_type == "ping":
                            logger.info("  → Ping message (responding with pong)")
                            await ws.send(json.dumps({"type": "pong"}))
                        elif msg_type == "error":
                            logger.error(f"  → Error message: {message.get('error', message)}")
                        else:
                            logger.warning(f"  → Unknown message type: {msg_type}")

                    logger.info("")

            except KeyboardInterrupt:
                logger.info("")
                logger.info("=" * 80)
                logger.info(f"Stopped listening. Received {message_count} messages total.")
                logger.info("=" * 80)
            finally:
                # Cancel ping task
                ping_task.cancel()
                try:
                    await ping_task
                except asyncio.CancelledError:
                    pass

    except websockets.exceptions.InvalidURI as e:
        logger.error(f"Invalid WebSocket URL: {e}")
        logger.info("Please verify the WebSocket URL in the script matches Polymarket docs")
        sys.exit(1)
    except websockets.exceptions.ConnectionClosed as e:
        logger.error(f"WebSocket connection closed: {e}")
        sys.exit(1)
    except OSError as e:
        if "No address associated with hostname" in str(e) or "Name or service not known" in str(e):
            logger.error(f"DNS resolution failed for {WS_USER_URL}")
            logger.error("Possible causes:")
            logger.error("  1. Incorrect WebSocket URL (check Polymarket docs)")
            logger.error("  2. Network/DNS issue")
            logger.error("  3. Firewall blocking connection")
            logger.info(f"  Verify URL: {WS_USER_URL}")
            logger.info(
                "  Docs: https://docs.polymarket.com/developers/CLOB/websocket/wss-overview"
            )
        else:
            logger.exception(f"Network error: {e}")
        sys.exit(1)
    except Exception as e:
        logger.exception(f"WebSocket error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(test_websocket_connection())
