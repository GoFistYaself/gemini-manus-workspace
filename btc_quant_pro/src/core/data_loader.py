import ccxt
import pandas as pd
import logging
import os
import time
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

class DataLoader:
    """Handles fetching and initial cleaning of market data using CCXT (Coinbase)."""
    
    _exchange = None

    @classmethod
    def _get_exchange(cls):
        if cls._exchange is None:
            load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "@.env"))
            api_key = os.getenv('COINBASE_API_KEY', '').strip('"')
            api_secret = os.getenv('COINBASE_API_SECRET', '').strip('"')
            
            cls._exchange = ccxt.coinbase({
                'apiKey': api_key,
                'secret': api_secret,
                'enableRateLimit': True
            })
        return cls._exchange

    @staticmethod
    def fetch_ohlcv(symbol: str, period: str = '30d', interval: str = '1h') -> pd.DataFrame:
        """
        Fetches OHLCV data from Coinbase.
        Note: CCXT uses 'timeframe' (1m, 5m, 1h) and 'limit' instead of 'period'.
        We map period to an approximate limit.
        """
        exchange = DataLoader._get_exchange()
        
        # Map Yahoo-style interval to CCXT timeframe
        # Note: Coinbase Advanced supports 1m, 5m, 15m, 1h, 6h, 1d
        timeframe_map = {
            '1m': '1m', '5m': '5m', '15m': '15m', 
            '1h': '1h', '4h': '1h', '1d': '1d'
        }
        tf = timeframe_map.get(interval, '1h')
        
        # Approximate limit based on period
        days = int(period.replace('d', '')) if 'd' in period else 30
        if tf == '1m': limit = min(1000, days * 1440)
        elif tf == '5m': limit = min(1000, days * 288)
        elif tf == '15m': limit = min(1000, days * 96)
        elif interval == '4h': limit = min(1000, days * 24) # Fetch 1h candles for 4h engine
        else: limit = min(1000, days * 24)

        logger.info(f"Fetching {tf} data for {symbol} from Coinbase (Limit: {limit})")
        
        try:
            ohlcv = exchange.fetch_ohlcv(symbol, timeframe=tf, limit=limit)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'Open', 'High', 'Low', 'Close', 'Volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df.set_index('timestamp', inplace=True)
            
            if df.empty:
                raise ValueError(f"No data fetched for {symbol}")
                
            return df
        except Exception as e:
            logger.error(f"CCXT Fetch Error for {symbol}: {e}")
            raise e
