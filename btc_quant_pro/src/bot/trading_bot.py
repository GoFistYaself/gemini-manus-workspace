import os
import sys
import time
import logging
import numpy as np
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv

# Internal dependencies
from src.core.signal_engine import SignalEngine
from src.core.pattern_engine import PatternEngine
from src.core.execution import PaperWallet, CoinbaseExecutionEngine
from src.core.indicators import IndicatorCalculator

# RL Agent (optional — graceful fallback if not trained yet)
try:
    from src.rl.rl_signal_engine import RLSignalEngine
    RL_AVAILABLE = True
except ImportError:
    RL_AVAILABLE = False

logger = logging.getLogger(__name__)


class AITradingBot:
    def __init__(self, name="ImprovedSniper-v7", symbol="BTC-USD", execution_engine=None):
        self.name = name.replace("/", "_").replace("-", "_")
        self.symbol = symbol
        # Stabilized intervals for Coinbase One
        self.intervals = ['1m', '5m', '15m', '1h']
        self.se = SignalEngine()
        self.pe = PatternEngine()
        self.wallet = execution_engine or PaperWallet(initial_balance=321.57)
        self.status = "INITIALIZING"
        self.risk_per_trade = 0.95  # HYPER VELOCITY (95% Capital Utilization)  # 20% default risk
        
        # MOTIVATION / PAIN SYSTEM
        self.points = 100
        self.last_profit_time = time.time()
        self.highest_recorded_equity = 0.0
        self.current_atr = 0.0
        self.rl_steps_in_pos = 0   # Track steps for RL observation

        # Initialize RL Signal Engine
        self.rl_engine = None
        if RL_AVAILABLE:
            try:
                self.rl_engine = RLSignalEngine()
                if self.rl_engine.is_ready():
                    logging.info("[RL] Phipps RL Agent loaded and ready.")
                else:
                    logging.info("[RL] Phipps RL Agent not trained yet. Run train_agent.py first.")
                    self.rl_engine = None
            except Exception as e:
                logging.warning(f"[RL] Could not initialize RL engine: {e}")
                self.rl_engine = None

    def _fetch_data(self, interval, limit=100):
        """Standardized Data Fetching with Indicator Injection."""
        try:
            exchange = getattr(self.wallet, 'exchange', None)
            if not exchange: return pd.DataFrame()
            
            ohlcv = exchange.fetch_ohlcv(self.symbol, timeframe=interval, limit=limit)
            if not ohlcv: return pd.DataFrame()
            
            df = pd.DataFrame(ohlcv, columns=['Timestamp', 'Open', 'High', 'Low', 'Close', 'Volume'])
            df['Timestamp'] = pd.to_datetime(df['Timestamp'], unit='ms')
            
            # Use project-standard IndicatorCalculator
            df = IndicatorCalculator.apply_indicators(df)
            return df
        except Exception as e:
            if "429" not in str(e):
                err_str = str(e).lower()
                if "does not have market symbol" in err_str or "symbol not found" in err_str:
                    logging.warning(f"Symbol {self.symbol} is delisted or missing. Skipping.")
                else:
                    logging.error(f"Fetch Error {interval}: {e}")
            return pd.DataFrame()

    def initialize(self):
        logging.info(f"[{self.name}] Initializing IMPROVED FLEET Sniper {self.symbol}...")
        try:
            # 1. Warm up Pattern Engine with historical context
            hist_df = self._fetch_data('1h', limit=250)
            if not hist_df.empty:
                self.pe.learn_performance(hist_df)
                self.se.pe.learn_performance(hist_df)
                logging.info(f"  [INIT] Pattern Engine Trained on {len(hist_df)} candles of {self.symbol}")
                logging.info(f"  [INIT] Knowledge Base: {self.pe.knowledge_base}")

            # 2. Reconcile balance
            usd, asset_bal = self.wallet.fetch_balance()
            price = self.wallet.get_latest_price() or 0.0
            
            # Re-read price if missing
            if price <= 0:
                df_init = self._fetch_data('1m', limit=5)
                price = df_init.iloc[-1]['Close'] if not df_init.empty else 0.0

            # Dust check ($10)
            if price > 0:
                min_notional = 10.0 / price
                if asset_bal > min_notional:
                    logging.info(f"  [RECONCILE] Found {self.symbol}: {asset_bal:.6f}")
                    self.wallet.position_size = asset_bal
                    self.wallet.entry_price = price
                else:
                    self.wallet.position_size = 0.0
            
            # 3. Report RL status
            if self.rl_engine and self.rl_engine.is_ready():
                logging.info(f"  [RL] Phipps Agent ACTIVE — contributing to voting system")
            else:
                logging.info(f"  [RL] Phipps Agent INACTIVE — train with: python train_agent.py")

            self.status = "SCANNING"
            logging.info(f"[{self.name}] IMPROVED v7.0 + RL Ready.")
        except Exception as e:
            logging.exception(f"Init Error: {e}")

    def live_tick(self):
        if self.status == "DEACTIVATED":
            return # Bot has died from too much pain.
            
        try:
            # --- MOTIVATION SYSTEM ---
            current_equity = getattr(self.wallet, 'equity', 0.0)
            now = time.time()
            
            if current_equity > self.highest_recorded_equity:
                if current_equity > self.highest_recorded_equity + 0.01: # Meaningful profit
                    self.last_profit_time = now
                    if self.points < 100:
                        self.points = min(100, self.points + 5)
                        logging.info(f"  [MOTIVATION] {self.symbol} made a profitable move! Relief felt. Points: {self.points}/100")
                self.highest_recorded_equity = current_equity
            
            # Check if 1 hour (3600 seconds) has passed without profit
            if now - self.last_profit_time > 3600:
                self.points -= 5
                self.last_profit_time = now # Reset timer so it hurts every hour
                logging.warning(f"  [PAIN] {self.symbol} has not made money in 1 hour. PAIN INDUCED. Points dropped to {self.points}/100")
                
                if self.points <= 0:
                    logging.critical(f"  [DEATH] {self.symbol} failed to be profitable. DEACTIVATED.")
                    self.status = "DEACTIVATED"
                    return
            # -------------------------
            # 1. Multi-Timeframe Analysis
            mtf = {}
            for intv in self.intervals:
                time.sleep(0.3)  # Rate limit safety
                df = self._fetch_data(intv, limit=60)
                if df.empty or len(df) < 30:
                    mtf[intv] = {'Signal': 0, 'Trend': 0, 'Close': 0}
                    continue
                
                # Signal Generation
                self.se.interval = intv
                scored_df = self.se.generate_signals(df, last_only=True)
                mtf[intv] = scored_df.iloc[-1].to_dict()
            
            current_price = self.wallet.get_latest_price() or mtf['1m'].get('Close')
            if not current_price: return

            # Update ATR from 1h data
            if 'ATR' in mtf.get('1h', {}):
                atr_val = mtf['1h']['ATR']
                if not pd.isna(atr_val):
                    self.current_atr = atr_val

            # 2. WEIGHTED VOTING (v7.5 + RL AGENT)
            w_votes = (
                mtf['1m'].get('Signal', 0) * 0.5 + 
                mtf['5m'].get('Signal', 0) * 1.0 + 
                mtf['15m'].get('Signal', 0) * 1.5 + 
                mtf['1h'].get('Signal', 0) * 2.0
            )

            # 3. RL AGENT VOTE (Phipps Strategy)
            rl_signal = 0
            rl_confidence = 0.0
            if self.rl_engine and self.rl_engine.is_ready():
                # Use 1h data row for RL observation (most complete indicators)
                rl_row = mtf.get('1h', {})
                if rl_row.get('Close', 0) > 0:
                    rl_signal, rl_confidence = self.rl_engine.get_signal_with_confidence(
                        row=rl_row,
                        position_size=self.wallet.position_size,
                        entry_price=self.wallet.entry_price,
                        steps_in_pos=self.rl_steps_in_pos,
                    )
                    # RL agent gets 2.5 weight (highest single vote — it's trained on this)
                    # But scaled by confidence so uncertain predictions don't dominate
                    rl_weight = 2.5 * rl_confidence
                    w_votes += rl_signal * rl_weight

            final_signal = 0
            if w_votes >= 0.8: final_signal = 1 # AGGRESSIVE
            if w_votes <= -0.8: final_signal = -1 # AGGRESSIVE
            
            self.wallet.update_equity(current_price)

            # Track steps in position for RL
            if self.wallet.position_size > 0:
                self.rl_steps_in_pos += 1
            else:
                self.rl_steps_in_pos = 0

            rl_str = f" | RL: {rl_signal}({rl_confidence:.0%})" if self.rl_engine else ""
            logging.info(
                f"Sym: {self.symbol} | Price: {current_price:.2f} | "
                f"Sig: {final_signal} | Votes: {w_votes:.2f}{rl_str} | "
                f"Eq: ${self.wallet.equity:.2f}"
            )
            
            self._execute_strategy(current_price, final_signal)
            
        except Exception as e:
            import traceback; logging.exception(f"Tick Error in {self.symbol}: {e}"); logging.error(traceback.format_exc())

    def _execute_strategy(self, price, signal):
        w = self.wallet

        # Position Exit (Aggressive on reverse signal)
        if w.position_size > 0 and signal == -1:
            logging.info(f"  [EXIT] Strong Reverse Signal for {self.symbol}")
            w.close_position(price, "REVERSE")
            return

        # ATR-based SL/TP (dynamic) or fallback to fixed
        if w.position_size > 0:
            if self.current_atr > 0:
                # Trailing stop is handled by execution engine's update_equity
                # But also check hard SL/TP
                if hasattr(w, 'stop_loss') and w.stop_loss > 0 and price < w.stop_loss:
                    w.close_position(price, "SL")
                elif hasattr(w, 'take_profit') and w.take_profit > 0 and price > w.take_profit:
                    w.close_position(price, "TP")
            else:
                # Fallback fixed SL/TP
                tp_target = 1.03 if getattr(w, 'cb_one', False) else 1.05
                sl_target = 0.985 if getattr(w, 'cb_one', False) else 0.98
                if price < w.entry_price * sl_target:
                    w.close_position(price, "SL")
                elif price > w.entry_price * tp_target:
                    w.close_position(price, "TP")

        # Entry Logic
        min_trade = 10.0 if getattr(w, 'cb_one', False) else 15.0
        is_dust = abs(w.position_size * price) < min_trade
        if (w.position_size == 0 or is_dust) and signal == 1:
            usd_bal, _ = w.fetch_balance()
            
            # HYPER VELOCITY: Allocate 95% of available capital per high-confidence trade
            # This ensures funds are always working and not sitting idle.
            trade_amt = usd_bal * 0.20
            if trade_amt < min_trade:
                trade_amt = usd_bal * 0.20  # Use all if balance low
            
            if trade_amt >= 10.0:  # Hard floor for Coinbase
                final_size = trade_amt / price

                # ASYMMETRIC TREND FOLLOWING (+EV Strategy)
                # Cut losers fast (1.5 ATR), let winners run (4.0+ ATR)
                if self.current_atr > 0:
                    sl = price - (1.0 * self.current_atr) 
                    tp = price + (6.0 * self.current_atr) # Aiming for massive risk/reward
                else:
                    sl = price * 0.95
                    tp = price * 1.15

                logging.info(
                    f"!!! [EXECUTE] BUY ${trade_amt:.2f} {self.symbol} | "
                    f"SL: {sl:.2f} | TP: {tp:.2f}"
                )
                w.open_position(price, final_size, sl, tp, 1.0,
                                atr_value=self.current_atr)

    def get_status_report(self):
        rl_status = "ACTIVE" if (self.rl_engine and self.rl_engine.is_ready()) else "INACTIVE"
        return (
            f"Bot: {self.name} | Equity: ${getattr(self.wallet, 'equity', 0.0):.2f} | "
            f"Pos: {getattr(self.wallet, 'position_size', 0.0):.4f} | "
            f"Life: {self.points}/100 | Status: {self.status}"
        )
