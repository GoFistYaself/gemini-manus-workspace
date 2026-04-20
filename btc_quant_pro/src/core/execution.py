import ccxt
import time
import os
import logging
import json
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()
# Also try loading from the specific @.env file if in the same dir
load_dotenv("@.env")

logger = logging.getLogger(__name__)

class ExecutionEngine:
    """Base class for execution engines."""
    def update_equity(self, current_price=None): pass
    def close_position(self, price, reason="Signal"): pass
    def open_position(self, price, size, stop_loss, take_profit, leverage): pass
    def get_status_report(self) -> str: return "Base Engine"
    def get_latest_price(self): return None

class PaperWallet(ExecutionEngine):
    def __init__(self, initial_balance=10000.0):
        self.balance = initial_balance
        self.equity = initial_balance
        self.position_size = 0.0 # BTC amount
        self.entry_price = 0.0
        self.stop_loss = 0.0
        self.take_profit = 0.0
        self.leverage = 1.0
        self.last_pnl = 0.0
        self.history = []
        self.last_price = 0.0
        self.history_file = os.path.join("logs", "paper_trade_history.json")
        
        # Ensure logs directory exists
        if not os.path.exists("logs"):
            os.makedirs("logs")

    def _log_trade(self, order_data):
        # We append to self.history, but also want to persist to disk for dashboard
        # Load existing if any to avoid overwrite on restart (optional, but good)
        # For simplicity, we'll just dump self.history which grows in memory
        try:
            with open(self.history_file, 'w') as f:
                json.dump(self.history, f, indent=4)
        except Exception as e:
            logger.error(f"Failed to write paper trade history: {e}")

    def update_equity(self, current_price=None):
        self.last_price = current_price
        if self.position_size != 0:
            pnl = (current_price - self.entry_price) * self.position_size
            self.equity = self.balance + pnl
        else:
            self.equity = self.balance

    def close_position(self, price, reason="Signal"):
        if self.position_size == 0: return
        
        pnl = (price - self.entry_price) * self.position_size
        self.last_pnl = pnl
        self.balance += pnl
        self.equity = self.balance
        
        trade_record = {
            "action": "CLOSE",
            "exit_price": price,
            "price": price, # Standardize for dashboard
            "pnl": pnl,
            "reason": reason,
            "direction": "SELL" if self.position_size > 0 else "BUY", # Closing Long = Sell
            "timestamp": datetime.now().isoformat()
        }
        self.history.append(trade_record)
        self._log_trade(trade_record)
        
        print(f"  >>> CLOSING POSITION ({reason}) @ {price:.2f} | PnL: ${pnl:.2f} | Eq: ${self.equity:.2f}")
        
        self.position_size = 0.0
        self.entry_price = 0.0
        self.stop_loss = 0.0
        self.take_profit = 0.0
        self.leverage = 1.0

    def open_position(self, price, size, stop_loss, take_profit, leverage):
        if self.position_size != 0:
            self.close_position(price, reason="Flip/Re-entry")
            
        cost = (price * abs(size)) / leverage
        if cost > self.balance:
            print("  !!! INSUFFICIENT MARGIN !!!")
            return

        self.position_size = size
        self.entry_price = price
        self.stop_loss = stop_loss
        self.take_profit = take_profit
        self.leverage = leverage
        
        direction = "LONG" if size > 0 else "SHORT"
        
        trade_record = {
            "action": "OPEN",
            "direction": direction,
            "amount": abs(size),
            "price": price,
            "timestamp": datetime.now().isoformat(),
            "sl": stop_loss,
            "tp": take_profit
        }
        self.history.append(trade_record)
        self._log_trade(trade_record)

        print(f"  >>> OPENING {direction} ({leverage}x) @ {price:.2f} | Size: {size:.4f} | SL: {stop_loss:.2f} | TP: {take_profit:.2f}")

    def get_status_report(self):
        return f"PaperWallet | Equity: ${self.equity:.2f} | Pos: {self.position_size:.4f} BTC"

    def get_latest_price(self):
        # In paper mode, price is pushed by the bot loop.
        # This method is mainly for the live engine to pull.
        return self.last_price

class CoinbaseExecutionEngine(ExecutionEngine):
    """
    Coinbase Advanced Trade Execution Engine using CCXT.
    Requires COINBASE_API_KEY and COINBASE_API_SECRET in environment.
    Includes a 'reserved_btc' vault to protect existing assets.
    """
    def __init__(self, symbol='BTC/USD', reserved_btc=0.0):
        self.symbol = symbol
        self.reserved_btc = reserved_btc
        api_key = os.getenv('COINBASE_API_KEY')
        api_secret = os.getenv('COINBASE_API_SECRET')
        
        # Strip quotes if they were included in .env
        if api_key: api_key = api_key.strip('"')
        if api_secret: api_secret = api_secret.strip('"')
        
        self.cached_usd = 0.0
        self.cached_btc = 0.0
        self.last_balance_fetch = 0
        
        if not api_key:
            print("[CRITICAL] Coinbase API Key not found in environment!")
        else:
            # Mask key for debug log
            print(f"[DEBUG] API Key loaded: {api_key[:10]}...{api_key[-10:]}")

        # Handle escaped newlines in PEM keys if present
        if api_secret:
            api_secret = api_secret.replace('\\n', '\n')

        self.exchange = ccxt.coinbase({
            'apiKey': api_key,
            'secret': api_secret,
            'enableRateLimit': True,
            'options': {
                'createMarketBuyOrderRequiresPrice': False
            }
        })
        self.position_size = 0.0
        self.entry_price = 0.0
        self.stop_loss = 0.0
        self.take_profit = 0.0
        self.leverage = 1.0
        self.equity = 0.0
        self.last_pnl = 0.0
        self.trade_history = []
        self.history_file = os.path.join(r"C:\Users\1mpal\logs", "coinbase_trade_history.json")
        self.state_file = os.path.join("logs", f"state_{self.symbol.replace('/', '_').replace('-', '_')}.json")

        # Trailing Stop Loss variables
        self.highest_price_since_entry = 0.0
        self.trailing_stop_loss = 0.0
        self.atr_value = 0.0
        
        # Trailing Stop Loss variables
        self.highest_price_since_entry = 0.0
        self.trailing_stop_loss = 0.0

        # Coinbase One / Zero Fee Mode
        self.cb_one = os.getenv('COINBASE_ONE', '0') == '1'
        self.fees_enabled = os.getenv('FEES_ENABLED', '1') == '1'
        
        if self.cb_one:
            print("[Coinbase] COINBASE ONE DETECTED: Zero-Fee Mode Active.")

        # Ensure logs directory exists
        if not os.path.exists("logs"):
            os.makedirs("logs")

        # Load state if exists
        self.load_state()

        # Verify connection
        try:
            self.exchange.check_required_credentials()
            print(f"[Coinbase] Credentials verified. Vault: {reserved_btc} BTC reserved.")
            self._verify_zero_fees() # Initial check
            self.fetch_balance(force=True)
            # self.update_equity() removed from init to prevent startup rate limits
        except Exception as e:
            print(f"[Coinbase] Credential Error: {e}")

    def save_state(self):
        """Persists current position and safety state to disk."""
        state = {
            "symbol": self.symbol,
            "position_size": self.position_size,
            "entry_price": self.entry_price,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "highest_price_since_entry": self.highest_price_since_entry,
            "trailing_stop_loss": self.trailing_stop_loss,
            "atr_value": self.atr_value,
            "timestamp": datetime.now().isoformat()
        }
        try:
            with open(self.state_file, 'w') as f:
                json.dump(state, f, indent=4)
        except Exception as e:
            logger.error(f"Failed to save state for {self.symbol}: {e}")

    def load_state(self):
        """Restores position and safety state from disk."""
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, 'r') as f:
                    state = json.load(f)
                    self.position_size = state.get("position_size", 0.0)
                    self.entry_price = state.get("entry_price", 0.0)
                    self.stop_loss = state.get("stop_loss", 0.0)
                    self.take_profit = state.get("take_profit", 0.0)
                    self.highest_price_since_entry = state.get("highest_price_since_entry", 0.0)
                    self.trailing_stop_loss = state.get("trailing_stop_loss", 0.0)
                    self.atr_value = state.get("atr_value", 0.0)
                    if self.position_size != 0:
                        print(f"  [MEMORY] Restored {self.symbol} position: {self.position_size:.6f} @ ${self.entry_price:.2f}")
            except Exception as e:
                logger.error(f"Failed to load state for {self.symbol}: {e}")

    def _verify_zero_fees(self):
        """
        Critical pre-trade check to ensure Coinbase One / Zero-Fee mode is active.
        """
        # Read file directly to bypass environment variable caching
        env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "@.env")
        if not os.path.exists(env_path): env_path = r"C:\Users\1mpal\btc_quant_pro\@.env"
        cb_one = False
        fees_enabled = True
        
        try:
            with open(env_path, 'r') as f:
                for line in f:
                    if line.startswith('COINBASE_ONE='):
                        cb_one = line.split('=')[1].strip().strip('"') == '1'
                    if line.startswith('FEES_ENABLED='):
                        fees_enabled = line.split('=')[1].strip().strip('"') == '1'
        except Exception as e:
            logger.error(f"Error reading {env_path} during verification: {e}")
            # If we can't read the file, fail safe (assume fees are enabled)
            return False
        
        if not cb_one or fees_enabled:
            msg = "[CRITICAL] COINBASE ONE / ZERO-FEE VERIFICATION FAILED! Trading halted."
            logger.critical(msg)
            print(msg)
            return False
            
        logger.info("[Coinbase] Verification successful: Coinbase One / Zero Fees confirmed.")
        return True

    def _log_trade(self, order_data):
        self.trade_history.append(order_data)
        
        # CRITICAL: Coinbase One Zero-Fee Enforcement
        fee = order_data.get('fee', 0.0)
        if fee > 0.0:
            msg = f"[CRITICAL] FEE DETECTED: ${fee:.4f} on {self.symbol} trade! Coinbase One may be inactive or limit reached."
            logger.critical(msg)
            print(msg)
            # We don't halt, but we alert.

        try:
            with open(self.history_file, 'w') as f:
                json.dump(self.trade_history, f, indent=4)
        except Exception as e:
            logger.error(f"Failed to write trade history: {e}")

    def fetch_balance(self, force=False):
        now = time.time()
        # Cache balance for 30 seconds
        if not force and now - self.last_balance_fetch < 30:
            return self.cached_usd, self.cached_btc
            
        try:
            balance = self.exchange.fetch_balance()
            usd = balance.get('USD', {}).get('free', 0.0)
            usdc = balance.get('USDC', {}).get('free', 0.0)
            usd += usdc # Support USDC as trading capital
            
            # Extract the base currency from symbol (e.g., BTC from BTC-USD or BTC/USD)
            base_currency = self.symbol.split('-')[0].split('/')[0]
            asset_balance = balance.get(base_currency, {}).get('free', 0.0)
            
            # For BTC, apply reserved_btc vault protection
            if base_currency == 'BTC':
                asset_balance = max(0.0, asset_balance - self.reserved_btc)
                
            self.cached_usd = usd
            self.cached_btc = asset_balance
            self.last_balance_fetch = now
            return usd, asset_balance
        except Exception as e:
            logger.error(f"Error fetching balance: {e}")
            return self.cached_usd, self.cached_btc

    def update_equity(self, current_price=None):
        now = time.time()
        # Cache total equity for 60 seconds to prevent rate-limiting and CPU spikes
        if hasattr(self, '_last_equity_update') and now - self._last_equity_update < 60:
            return self.equity

        totals = {}
        try:
            balance = self.exchange.fetch_balance()
            total_equity = 0.0
            
            # Use the 'total' dictionary which is more reliable across CCXT versions
            totals = balance.get('total', {})
            if not totals:
                 # Fallback for different CCXT structures
                 for asset, data in balance.items():
                    if isinstance(data, dict) and 'total' in data:
                        totals[asset] = data['total']

            # 1. Sum up all non-zero assets
            for asset, amount in totals.items():
                if amount <= 0: continue
                
                # Treat stablecoins as $1
                if asset in ['USD', 'USDC', 'USDT', 'DAI', 'PYUSD']:
                    total_equity += amount
                    continue
                
                # Fetch price for other assets
                try:
                    # Use current_price if it matches our primary symbol
                    if asset in self.symbol and current_price is not None:
                        price = current_price
                    else:
                        # Fetch ticker for other assets (BTC, SOL, etc.)
                        # We use a common symbol format for price fetching
                        price_sym = f"{asset}-USD"
                        ticker = self.exchange.fetch_ticker(price_sym)
                        price = ticker['last']
                    
                    if price is not None: total_equity += (amount * price)
                except Exception as e:
                    # Log but keep going - don't let one bad ticker kill the whole calc
                    if asset in ['BTC', 'SOL']:
                        logger.warning(f"Failed to fetch price for core asset {asset}: {e}")
                    # If we can't get the price, we just don't add it (conservative)
            
            self.equity = total_equity
            self._last_equity_update = now
            self.save_state()
            
            # Final safety check
            if self.equity <= 0:
                 self.equity = totals.get('USD', 0.0) + totals.get('USDC', 0.0)
                 
        except Exception as e:
            logger.error(f"Error calculating total equity: {e}")
            if current_price: 
                # Very rough fallback
                usd = totals.get('USD', 0.0) + totals.get('USDC', 0.0)
                self.equity = usd + (totals.get('BTC', 0.0) * current_price)
        
        # Trailing Stop Loss Update
        if self.position_size > 0 and current_price is not None and self.trailing_stop_loss > 0:
            self.highest_price_since_entry = max(self.highest_price_since_entry, current_price)
            # Trailing stop moves up with price, but never down
            new_trailing_stop = self.highest_price_since_entry - (self.atr_value * 0.3)
            self.trailing_stop_loss = max(self.trailing_stop_loss, new_trailing_stop)
            
            if current_price <= self.trailing_stop_loss:
                logger.info(f"Trailing Stop Loss hit at {current_price:.2f}. Closing position.")
                self.close_position(current_price, reason="Trailing SL")

        return self.equity

    def open_position(self, price, size, stop_loss, take_profit, leverage, atr_value=0.0):
        """
        Executes a Market Buy
        """
        if not self._verify_zero_fees():
             return False

        # Force a fresh balance fetch before opening to avoid stale cache in multi-bot fleet
        self.fetch_balance(force=True)

        direction = "BUY" if size > 0 else "SELL"
        
        if direction == "SELL":
            usd, tradable_asset = self.fetch_balance()
            # If we don't have enough 'tradable' from internal state, check the actual exchange balance
            if abs(size) > tradable_asset:
                logging.info(f"  [SAVAGE] Signal: SELL. Current holdings: {tradable_asset:.6f}. Size: {abs(size):.6f}.")
                # Shorting simulation: Sell EVERYTHING we have of this asset
                size = -tradable_asset
                if size == 0: 
                    logging.info(f"  [SAVAGE] No holdings of {self.symbol} to sell for pseudo-short.")
                    return False

        logging.info(f"  [COINBASE] Executing {direction} order for {abs(size):.4f} {self.symbol}")
        
        try:
            if size > 0:
                # Coinbase Advanced requires Market Buys to be defined in quote currency (USD)
                # cost = size (base) * price
                cost = abs(size) * price
                order = self.exchange.create_order(
                    self.symbol, 
                    'market', 
                    'buy', 
                    None,  # amount is None for quote-based market buys
                    None,  # price is None
                    {'cost': cost} # Pass the USD cost via options
                )
            else:
                # Use standard market sell (sells the base asset amount)
                order = self.exchange.create_market_sell_order(self.symbol, abs(size))
            
            # Record detailed order info
            filled_price = order.get('average') or order.get('price') or price
            fee = 0.0 if self.cb_one else (order.get('fee', {}).get('cost', 0.0) if order.get('fee') else 0.0)
            
            # CRITICAL SAFETY: Only update state if we have a valid price
            if filled_price is None:
                print(f"  !!! COINBASE ERROR: Order returned NULL price. Aborting state update.")
                return False

            order_record = {
                "action": "OPEN",
                "direction": direction,
                "order_id": order.get('id'),
                "symbol": self.symbol,
                "amount": order.get('amount', abs(size)),
                "price": filled_price,
                "fee": fee,
                "timestamp": datetime.now().isoformat(),
                "sl": stop_loss,
                "tp": take_profit
            }
            self._log_trade(order_record)
            self.save_state()
            
            self.entry_price = float(filled_price)
            self.position_size = size
            self.stop_loss = float(stop_loss)
            self.take_profit = float(take_profit)
            self.leverage = leverage
            
            # Initialize trailing stop loss
            self.highest_price_since_entry = filled_price
            self.atr_value = atr_value
            self.trailing_stop_loss = filled_price - (atr_value * 0.3) if atr_value > 0 else 0.0

            msg = f"  >>> COINBASE {direction} SUCCESS | ID: {order.get('id')} | Price: {filled_price}"
            print(msg)
            logger.info(msg)
            return True
        except Exception as e:
            err_msg = f"  !!! COINBASE ORDER FAILED for {self.symbol}: {e}"
            print(err_msg)
            logger.error(err_msg)
            return False

    def close_position(self, price, reason="Signal"):
        if not self._verify_zero_fees():
             return False
             
        if self.position_size == 0: return False
        
        logging.info(f"  [COINBASE] Closing position: {reason}")
        direction = "SELL" if self.position_size > 0 else "BUY"
        
        # Safety Check for Sell
        if direction == "SELL":
            usd, tradable_btc = self.fetch_balance()
            if abs(self.position_size) > tradable_btc:
                print(f"  [VAULT PROTECT] Capping sell to tradable amount.")
                self.position_size = tradable_btc
                if self.position_size <= 0: return False

        try:
            if self.position_size > 0:
                order = self.exchange.create_market_sell_order(self.symbol, abs(self.position_size))
            else:
                # If shorting, close position by buying back
                # Pass the cost in USD like we did for opening
                cost = abs(self.position_size) * price
                order = self.exchange.create_order(
                    self.symbol, 'market', 'buy', None, None, {'cost': cost}
                )
            
            filled_price = order.get('average') or order.get('price') or price
            fee = 0.0 if self.cb_one else (order.get('fee', {}).get('cost', 0.0) if order.get('fee') else 0.0)
            
            # Ensure filled_price is valid before calculating PNL
            if filled_price is None: filled_price = price
            
            pnl = (filled_price - self.entry_price) * self.position_size if self.entry_price else 0
            self.last_pnl = pnl
            
            order_record = {
                "action": "CLOSE",
                "reason": reason,
                "order_id": order.get('id'),
                "price": filled_price,
                "fee": fee,
                "pnl": pnl,
                "timestamp": datetime.now().isoformat()
            }
            self._log_trade(order_record)
            self.save_state()
            
            print(f"  >>> COINBASE POSITION CLOSED ({reason}) | PnL: ${pnl:.2f}")
            self.position_size = 0.0
            self.entry_price = 0.0
            self.stop_loss = 0.0
            self.take_profit = 0.0
            self.leverage = 1.0
            self.highest_price_since_entry = 0.0 # Reset for next trade
            self.trailing_stop_loss = 0.0 # Reset for next trade
            self.atr_value = 0.0 # Reset for next trade
            return True
        except Exception as e:
            print(f"  !!! COINBASE CLOSE FAILED: {e}")
            return False

    def get_status_report(self):
        usd, btc = self.fetch_balance()
        trades_count = len([t for t in self.trade_history if t['action'] == 'CLOSE'])
        return f"Exchange: Coinbase | USD: ${usd:.2f} | BTC: {btc:.4f} | Trades: {trades_count}"
