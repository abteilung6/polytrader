"""
Coinbase price data adapter for fetching ETH/USD candles.

Reuses code from flexible_price_tracker.py to fetch the latest candle
for a given timeframe.
"""

import requests
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict


# Timeframe configurations
TIMEFRAME_CONFIGS: Dict[str, Dict] = {
    'eth': {
        'granularity': 900,      # 15 minutes in seconds
        'name': 'ETH 15min',
    },
    'eth_1h': {
        'granularity': 3600,     # 1 hour in seconds
        'name': 'ETH 1h',
    },
    'eth_4h': {
        'granularity': 14400,    # 4 hours in seconds
        'name': 'ETH 4h',
    },
    'eth_1d': {
        'granularity': 86400,    # 1 day in seconds
        'name': 'ETH 1d',
    },
}


class CoinbaseCandleFetcher:
    """Fetches the latest ETH/USD candle from Coinbase with flexible timeframes"""
    
    BASE_URL = "https://api.exchange.coinbase.com"
    PRODUCT_ID = "ETH-USD"
    
    def __init__(self, timeframe: str = 'eth'):
        """
        Initialize fetcher for a specific timeframe
        
        Args:
            timeframe: One of 'eth', 'eth_1h', 'eth_4h', 'eth_1d'
        """
        if timeframe not in TIMEFRAME_CONFIGS:
            raise ValueError(f"Unknown timeframe: {timeframe}. Choose from: {list(TIMEFRAME_CONFIGS.keys())}")
        
        self.timeframe = timeframe
        self.config = TIMEFRAME_CONFIGS[timeframe]
        self.granularity = self.config['granularity']
        
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Polytrader/1.0'
        })
    
    def fetch_latest_candle(self) -> Optional[Dict]:
        """
        Fetch the latest completed candle from Coinbase
        
        Returns:
            Dictionary with candle data (timestamp, open, high, low, close, volume)
            or None if fetch fails
        """
        url = f"{self.BASE_URL}/products/{self.PRODUCT_ID}/candles"
        
        # Fetch last 2 candles to ensure we get the latest completed one
        # Calculate start time: go back 2 * granularity to get at least 2 candles
        now = datetime.now(timezone.utc)
        start_time = now - timedelta(seconds=self.granularity * 2)
        
        params = {
            "granularity": self.granularity,
            "start": start_time.isoformat(),
            "end": now.isoformat(),
        }
        
        try:
            response = self.session.get(url, params=params, timeout=5)
            response.raise_for_status()
            
            data = response.json()
            
            if not data:
                return None
            
            # Coinbase returns: [timestamp, low, high, open, close, volume]
            # Sort by timestamp (ascending) and get the latest (last) candle
            candles = sorted(data, key=lambda x: x[0])
            
            if not candles:
                return None
            
            # Get the latest candle
            latest = candles[-1]
            
            # Convert timestamp to datetime
            timestamp = datetime.fromtimestamp(latest[0], tz=timezone.utc)
            
            return {
                'timestamp': timestamp,
                'open': float(latest[3]),
                'high': float(latest[2]),
                'low': float(latest[1]),
                'close': float(latest[4]),
                'volume': float(latest[5]),
            }
        except requests.exceptions.RequestException as e:
            print(f"⚠️  Error fetching candle from Coinbase: {e}")
            return None
    
    def get_current_price(self) -> Optional[Dict]:
        """Fetch current real-time ETH price"""
        try:
            url = f"{self.BASE_URL}/products/{self.PRODUCT_ID}/ticker"
            response = self.session.get(url, timeout=5)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"⚠️  Error fetching current price from Coinbase: {e}")
            return None

