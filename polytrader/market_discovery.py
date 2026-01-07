"""Market slug discovery and generation based on asset and time period."""

from datetime import datetime, timezone
from typing import Literal

try:
    from zoneinfo import ZoneInfo
except ImportError:
    # Python < 3.9 fallback
    try:
        from backports.zoneinfo import ZoneInfo  # type: ignore
    except ImportError:
        # If zoneinfo not available, use UTC-5 offset (simplified, no DST)
        ZoneInfo = None  # type: ignore

Asset = Literal["bitcoin", "ethereum", "btc", "eth"]
TimePeriod = Literal["15m", "1h"]


class MarketSlugGenerator:
    """Generates the latest Polymarket market slug based on asset and time period."""

    @staticmethod
    def normalize_asset(asset: str) -> tuple[str, str]:
        """Normalize asset name to both formats.
        
        Returns:
            Tuple of (short_format, long_format)
            e.g., ("btc", "bitcoin") or ("eth", "ethereum")
        """
        asset_lower = asset.lower()
        if asset_lower in ("bitcoin", "btc"):
            return ("btc", "bitcoin")
        elif asset_lower in ("ethereum", "eth"):
            return ("eth", "ethereum")
        else:
            raise ValueError(f"Unknown asset: {asset}. Supported: bitcoin, btc, ethereum, eth")

    @staticmethod
    def normalize_time_period(period: str) -> str:
        """Normalize time period string.
        
        Only supports: "15m" for 15-minute markets, "1h" for hourly markets.
        """
        period_lower = period.lower()
        if period_lower == "15m":
            return "15min"
        elif period_lower == "1h":
            return "1h"
        else:
            raise ValueError(f"Unknown time period: {period}. Supported: 15m, 1h")

    @staticmethod
    def get_latest_15min_slug(asset: str) -> str:
        """Generate the latest 15-minute market slug.
        
        Format: {asset}-updown-15m-{timestamp}
        Timestamp is aligned to the next 15-minute interval (round up).
        """
        short_format, _ = MarketSlugGenerator.normalize_asset(asset)
        
        # Get current UTC time
        now_utc = datetime.now(timezone.utc)
        current_timestamp = int(now_utc.timestamp())
        
        # Align to the current 15-minute interval (round down)
        # This gets the currently active market
        # 15 minutes = 900 seconds
        aligned_timestamp = (current_timestamp // 900) * 900
        
        return f"{short_format}-updown-15m-{aligned_timestamp}"

    @staticmethod
    def get_latest_hourly_slug(asset: str) -> str:
        """Generate the latest hourly market slug.
        
        Format: {asset}-up-or-down-{month}-{day}-{hour}am-et
        Uses ET timezone and rounds down to the current hour.
        """
        _, long_format = MarketSlugGenerator.normalize_asset(asset)
        
        # Get current UTC time
        now_utc = datetime.now(timezone.utc)
        
        # Convert to ET (handles DST automatically)
        if ZoneInfo is not None:
            et_tz = ZoneInfo("America/New_York")
            now_et = now_utc.astimezone(et_tz)
        else:
            # Fallback: use UTC-5 (simplified, doesn't handle DST)
            # Convert UTC to ET: ET is UTC-5, so subtract 5 hours from UTC time
            from datetime import timedelta
            et_offset = timedelta(hours=-5)
            et_tz_fallback = timezone(et_offset, name="ET")
            # Get ET time: add negative offset (which subtracts 5 hours)
            et_time_naive = now_utc.replace(tzinfo=None) + et_offset
            now_et = et_time_naive.replace(tzinfo=et_tz_fallback)
        
        # Round down to current hour
        current_hour = now_et.replace(minute=0, second=0, microsecond=0)
        
        # Format date components
        month_name = current_hour.strftime("%B").lower()  # january, february, etc.
        day = current_hour.day
        hour_12 = current_hour.hour % 12
        if hour_12 == 0:
            hour_12 = 12
        am_pm = "am" if current_hour.hour < 12 else "pm"
        
        return f"{long_format}-up-or-down-{month_name}-{day}-{hour_12}{am_pm}-et"

    @classmethod
    def get_latest_slug(cls, asset: str, time_period: str) -> str:
        """Get the latest market slug for the given asset and time period.
        
        Args:
            asset: Asset name (bitcoin, btc, ethereum, eth)
            time_period: Time period - "15m" (15-minute) or "1h" (hourly)
            
        Returns:
            Latest market slug string
            
        Examples:
            >>> MarketSlugGenerator.get_latest_slug("bitcoin", "15m")
            'btc-updown-15m-1767709800'
            >>> MarketSlugGenerator.get_latest_slug("ethereum", "1h")
            'ethereum-up-or-down-january-6-9am-et'
        """
        period = cls.normalize_time_period(time_period)
        
        if period == "15min":
            return cls.get_latest_15min_slug(asset)
        elif period == "1h":
            return cls.get_latest_hourly_slug(asset)
        else:
            raise ValueError(f"Unsupported time period: {time_period}")

    @staticmethod
    def get_market_expiration_time(market_slug: str) -> datetime | None:
        """Get the expiration time for a market based on its slug.
        
        Args:
            market_slug: Market slug (e.g., "btc-updown-15m-1767709800" or "bitcoin-up-or-down-january-6-9am-et")
            
        Returns:
            Expiration datetime in UTC, or None if slug format is not recognized
        """
        # Check if it's a 15-minute market: {asset}-updown-15m-{timestamp}
        if "-updown-15m-" in market_slug:
            try:
                timestamp_str = market_slug.split("-updown-15m-")[-1]
                start_timestamp = int(timestamp_str)
                # Market expires 15 minutes (900 seconds) after start
                expiration_timestamp = start_timestamp + 900
                return datetime.fromtimestamp(expiration_timestamp, tz=timezone.utc)
            except (ValueError, IndexError):
                return None
        
        # Check if it's an hourly market: {asset}-up-or-down-{month}-{day}-{hour}am-et
        if "-up-or-down-" in market_slug and "-et" in market_slug:
            try:
                # Parse the date part: e.g., "january-6-9am"
                date_part = market_slug.split("-up-or-down-")[-1].replace("-et", "")
                parts = date_part.split("-")
                
                if len(parts) < 3:
                    return None
                
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
                    return None
                
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
                    return None
                
                # Create datetime in ET timezone
                if ZoneInfo is not None:
                    et_tz = ZoneInfo("America/New_York")
                    market_start_et = datetime(year, month, day, hour, 0, 0, tzinfo=et_tz)
                else:
                    from datetime import timedelta
                    et_offset = timedelta(hours=-5)
                    et_tz_fallback = timezone(et_offset, name="ET")
                    market_start_et = datetime(year, month, day, hour, 0, 0, tzinfo=et_tz_fallback)
                
                # Convert to UTC
                market_start_utc = market_start_et.astimezone(timezone.utc)
                
                # Market expires 1 hour after start
                from datetime import timedelta
                expiration_utc = market_start_utc + timedelta(hours=1)
                return expiration_utc
            except (ValueError, IndexError, KeyError):
                return None
        
        return None

