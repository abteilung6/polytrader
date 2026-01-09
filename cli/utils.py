"""Shared utilities for CLI commands."""

import asyncio
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from polytrader.adapters.polymarket import PolymarketAdapterConfig, PolymarketMarketDataAdapter
from polytrader.config import PolymarketSecrets
from polytrader.events import EventBus
from polytrader.market_discovery import MarketSlugGenerator
from polytrader.observer import Observer
from polytrader.store import MemoryTickStore

if TYPE_CHECKING:
    from polytrader.types import Outcome


def get_current_interval_id(asset: str, time_period: str) -> str:
    """Get current interval identifier for checking if market slug needs refresh.
    
    For 15-minute markets: returns the aligned timestamp string
    For hourly markets: returns the hour identifier string (month-day-hour-am/pm)
    """
    period = MarketSlugGenerator.normalize_time_period(time_period)
    
    if period == "15min":
        # Return the current 15-minute interval (round down)
        # This gets the currently active market
        now_utc = datetime.now(timezone.utc)
        current_timestamp = int(now_utc.timestamp())
        aligned_timestamp = (current_timestamp // 900) * 900
        return str(aligned_timestamp)
    elif period == "1h":
        # Return hour identifier
        _, long_format = MarketSlugGenerator.normalize_asset(asset)
        slug = MarketSlugGenerator.get_latest_hourly_slug(asset)
        # Extract the hour part: {asset}-up-or-down-{month}-{day}-{hour}am-et
        parts = slug.split("-")
        # Return everything after "up-or-down" as identifier
        return "-".join(parts[3:])  # month-day-hour-am-et
    else:
        raise ValueError(f"Unsupported time period: {time_period}")


async def create_observers(
    market_slug: str,
    outcomes_to_watch: list[str],
    secrets: PolymarketSecrets,
    frequency: float,
    bus: EventBus,
    store: MemoryTickStore,
) -> tuple[list[Observer], list[asyncio.Task]]:
    """Create observers for the given market slug."""
    observers = []
    observer_tasks = []
    
    for outcome_cli in outcomes_to_watch:
        outcome_type: "Outcome" = "UP" if outcome_cli == "Up" else "DOWN"
        
        config = PolymarketAdapterConfig(
            market_slug=market_slug,
            outcome=outcome_type,
            polling_frequency_hz=frequency,
            secrets=secrets,
        )
        
        adapter = PolymarketMarketDataAdapter(config)
        observer = Observer(bus, adapter, store)
        observers.append(observer)
        observer_tasks.append(asyncio.create_task(observer.run()))
    
    return observers, observer_tasks


async def stop_observers(observers: list[Observer], observer_tasks: list[asyncio.Task]) -> None:
    """Stop observers and cancel their tasks."""
    for observer in observers:
        observer.stop()
    for task in observer_tasks:
        task.cancel()
    for task in observer_tasks:
        try:
            await task
        except asyncio.CancelledError:
            pass


def get_market_timestamp(market_slug: str) -> datetime:
    """Extract timestamp from market slug and return as datetime.
    
    For 15-minute markets: extracts timestamp from slug (e.g., btc-updown-15m-1767712500)
    For hourly markets: parses date/time from slug format (e.g., bitcoin-up-or-down-january-6-9am-et)
    """
    # Check if it's a 15-minute market: {asset}-updown-15m-{timestamp}
    if "-updown-15m-" in market_slug:
        try:
            timestamp_str = market_slug.split("-updown-15m-")[-1]
            timestamp = int(timestamp_str)
            return datetime.fromtimestamp(timestamp, tz=timezone.utc)
        except (ValueError, IndexError):
            raise ValueError(f"Could not parse timestamp from market slug: {market_slug}")
    
    # Check if it's an hourly market: {asset}-up-or-down-{month}-{day}-{hour}am-et
    if "-up-or-down-" in market_slug and "-et" in market_slug:
        try:
            # Parse the date part: e.g., "january-6-9am"
            date_part = market_slug.split("-up-or-down-")[-1].replace("-et", "")
            parts = date_part.split("-")
            
            if len(parts) < 3:
                raise ValueError(f"Could not parse date from market slug: {market_slug}")
            
            month_name = parts[0]
            day = int(parts[1])
            hour_str = parts[2]
            
            # Parse hour (e.g., "9am" or "2pm")
            if hour_str.endswith("am"):
                hour = int(hour_str[:-2])
                if hour == 12:
                    hour = 0
            elif hour_str.endswith("pm"):
                hour = int(hour_str[:-2])
                if hour != 12:
                    hour += 12
            else:
                raise ValueError(f"Could not parse hour from market slug: {market_slug}")
            
            # Get current year (markets are typically for current year)
            now_utc = datetime.now(timezone.utc)
            year = now_utc.year
            
            # Convert month name to number
            month_map = {
                "january": 1, "february": 2, "march": 3, "april": 4,
                "may": 5, "june": 6, "july": 7, "august": 8,
                "september": 9, "october": 10, "november": 11, "december": 12
            }
            month = month_map.get(month_name.lower())
            if month is None:
                raise ValueError(f"Unknown month name: {month_name}")
            
            # Create datetime in ET timezone
            try:
                from zoneinfo import ZoneInfo
            except ImportError:
                try:
                    from backports.zoneinfo import ZoneInfo  # type: ignore
                except ImportError:
                    ZoneInfo = None  # type: ignore
            
            if ZoneInfo is not None:
                et_tz = ZoneInfo("America/New_York")
                market_start_et = datetime(year, month, day, hour, 0, 0, tzinfo=et_tz)
            else:
                from datetime import timedelta
                et_offset = timedelta(hours=-5)
                et_tz_fallback = timezone(et_offset, name="ET")
                market_start_et = datetime(year, month, day, hour, 0, 0, tzinfo=et_tz_fallback)
            
            # Convert to UTC
            return market_start_et.astimezone(timezone.utc)
        except (ValueError, IndexError, KeyError) as e:
            raise ValueError(f"Could not parse date/time from market slug: {market_slug}") from e
    
    raise ValueError(f"Unknown market slug format: {market_slug}")


def resolve_market_slug(asset: str | None, time_period: str | None, market: str | None) -> tuple[str, bool]:
    """Resolve market slug from arguments.
    
    Args:
        asset: Asset name (optional)
        time_period: Time period (optional)
        market: Market slug (optional)
    
    Returns:
        Tuple of (market_slug, auto_refresh_enabled)
    
    Raises:
        ValueError: If arguments are invalid
    """
    auto_refresh = asset is not None and time_period is not None
    
    if auto_refresh:
        market_slug = MarketSlugGenerator.get_latest_slug(asset, time_period)
        return market_slug, True
    elif market:
        return market, False
    else:
        raise ValueError("Either --market or both --asset and --time-period must be provided")

