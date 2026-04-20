import ccxt
import time
import os
import logging
import json
from dotenv import load_dotenv
from datetime import datetime

# Load env vars
load_dotenv()
load_dotenv("@.env")

logger = logging.getLogger(__name__)

class CoinbaseFuturesEngine:
    """
    Experimental Coinbase Advanced Trade Futures Execution Engine.
    Requires manual onboarding to Futures in the Coinbase UI.
    Requires USDC in the 'Perpetuals Portfolio'.
    """
    def __init__(self, symbol='BTC-USDC-PERP'):
        self.symbol = symbol # e.g., 'BTC-USDC-PERP'
        api_key = os.getenv('COINBASE_API_KEY')
        api_secret = os.getenv('COINBASE_API_SECRET')
        
        if api_secret:
            api_secret = api_secret.replace('\\n', '\n')

        # Use the base 'coinbase' class for Futures
        self.exchange = ccxt.coinbase({
            'apiKey': api_key,
            'secret': api_secret,
            'enableRateLimit': True,
            'options': {
                'defaultType': 'future'
            }
        })
        
        self.position_size = 0.0 # Positive for Long, Negative for Short
        self.entry_price = 0.0
        self.leverage = 1.0
        self.equity = 0.0
        self.available_margin = 0.0
        self.trade_history = []
        self.history_file = os.path.join("logs", "futures_trade_history.json")

        if not os.path.exists("logs"):
            os.makedirs("logs")

        # Verify connection and load markets
        try:
            self.exchange.load_markets()
            print(f"[FUTURES] Connected. Trading {self.symbol}")
            self.update_equity()
        except Exception as e:
            print(f"[FUTURES] Connection Error: {e}")

    def _log_trade(self, order_data):
        self.trade_history.append(order_data)
        try:
            with open(self.history_file, 'w') as f:
                json.dump(self.trade_history, f, indent=4)
        except Exception as e:
            logger.error(f"Failed to write futures trade history: {e}")

    def update_equity(self, current_price=None):
        """Fetches perpetual portfolio balance and open positions."""
        try:
            # Coinbase Futures balance is in a specific 'future' account type
            balance = self.exchange.fetch_balance({'type': 'future'})
            
            # USDC is the main collateral for Coinbase Perps
            usdc_info = balance.get('USDC', {})
            self.available_margin = usdc_info.get('free', 0.0)
            self.equity = usdc_info.get('total', 0.0)
            
            # Sync position from exchange
            positions = self.exchange.fetch_positions([self.symbol])
            if positions:
                pos = positions[0]
                self.position_size = float(pos.get('contracts', 0.0))
                if pos.get('side') == 'short':
                    self.position_size *= -1
                self.entry_price = float(pos.get('entryPrice', 0.0))
                self.leverage = float(pos.get('leverage', 1.0))
                
        except Exception as e:
            logger.error(f"Futures Equity Update Failed: {e}")

    def open_position(self, price, size, stop_loss, take_profit, leverage):
        """
        Opens a Long or Short position on Coinbase Futures.
        size: positive for Long, negative for Short.
        """
        side = 'buy' if size > 0 else 'sell'
        amount = abs(size)
        
        print(f"  [FUTURES] Opening {side.upper()} position | Size: {amount} | Lev: {leverage}x")
        
        try:
            # 1. Set Leverage first
            try:
                self.exchange.set_leverage(leverage, self.symbol)
            except Exception as e:
                print(f"  [FUTURES] Warning setting leverage: {e}")

            # 2. Place Market Order
            # Note: Coinbase Futures often require limit orders with aggressive prices for better execution,
            # but we'll try market first if supported by CCXT for this endpoint.
            order = self.exchange.create_order(self.symbol, 'market', side, amount)
            
            filled_price = order.get('average', order.get('price', price))
            
            order_record = {
                "action": "OPEN",
                "side": side,
                "symbol": self.symbol,
                "amount": amount,
                "price": filled_price,
                "leverage": leverage,
                "timestamp": datetime.now().isoformat(),
                "sl": stop_loss,
                "tp": take_profit
            }
            self._log_trade(order_record)
            
            # Update internal state
            self.update_equity()
            return True
        except Exception as e:
            print(f"  !!! FUTURES OPEN FAILED: {e}")
            return False

    def close_position(self, price, reason="Signal"):
        if self.position_size == 0: return False
        
        # To close a position, we go the opposite way
        side = 'sell' if self.position_size > 0 else 'buy'
        amount = abs(self.position_size)
        
        print(f"  [FUTURES] Closing position: {reason} | Amount: {amount}")
        
        try:
            order = self.exchange.create_order(self.symbol, 'market', side, amount)
            filled_price = order.get('average', order.get('price', price))
            
            order_record = {
                "action": "CLOSE",
                "reason": reason,
                "price": filled_price,
                "timestamp": datetime.now().isoformat()
            }
            self._log_trade(order_record)
            
            self.position_size = 0.0
            self.entry_price = 0.0
            self.update_equity()
            return True
        except Exception as e:
            print(f"  !!! FUTURES CLOSE FAILED: {e}")
            return False

    def get_status_report(self):
        side_str = "LONG" if self.position_size > 0 else "SHORT" if self.position_size < 0 else "NONE"
        return f"Futures: {self.symbol} | Equity: ${self.equity:.2f} | Pos: {side_str} ({abs(self.position_size)})"
