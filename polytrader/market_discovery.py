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
        Timestamp is aligned to the nearest 15-minute interval (past).
        """
        short_format, _ = MarketSlugGenerator.normalize_asset(asset)
        
        # Get current UTC time
        now_utc = datetime.now(timezone.utc)
        current_timestamp = int(now_utc.timestamp())
        
        # Align to the nearest 15-minute interval (round down)
        # 15 minutes = 900 seconds
        aligned_timestamp = current_timestamp - (current_timestamp % 900)
        
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

