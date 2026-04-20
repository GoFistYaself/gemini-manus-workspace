"""
Phipps Trading Environment - Custom Gym Environment for RL-based BTC Trading.

Key Features (from Phipps Strategy):
1. NORMALIZATION: Observations use distance-to-SMA instead of raw price,
   so the agent generalizes across any price level ($10k or $100k).
2. LIFE PENALTY: -0.01 reward per step of inactivity. The agent is
   "slowly bleeding out" and MUST find trades to survive.
3. RIBBON KISS BONUS: Extra reward when the agent trades near the EMA 50
   touch ("Yellow Circle" logic). The agent learns to hunt these setups.

Observation Space (14 features, all normalized):
  0: close_dist_sma20    - Distance from Close to SMA20 (normalized by SMA20)
  1: close_dist_sma50    - Distance from Close to SMA50 (normalized by SMA50)
  2: close_dist_ema200   - Distance from Close to EMA200 (normalized by EMA200)
  3: ema20_above_ema50   - 1.0 if EMA20 > EMA50, else -1.0 (trend direction)
  4: rsi_norm            - RSI normalized to [-1, 1] range (rsi - 50) / 50
  5: macd_hist_norm      - MACD Histogram normalized by ATR
  6: atr_pct             - ATR as percentage of price (volatility measure)
  7: volume_ratio        - Current volume / Volume SMA (volume surge indicator)
  8: adx_norm            - ADX normalized to [0, 1] range (trend strength)
  9: choppiness_norm     - Choppiness Index normalized to [0, 1]
  10: ribbon_kiss        - 1.0 if price is within 0.3% of EMA50, else 0.0
  11: position_flag      - 1.0 if holding, 0.0 if flat
  12: unrealized_pnl     - Current unrealized PnL as % of entry (if holding)
  13: time_in_position   - Steps held in current position (normalized, max 100)

Action Space (Discrete, 3 actions):
  0: HOLD / DO NOTHING
  1: BUY (open long or hold existing long)
  2: SELL (close long position)
"""

import gymnasium as gym
from gymnasium import spaces
import numpy as np
import pandas as pd
import logging

logger = logging.getLogger(__name__)


class PhippsTradingEnv(gym.Env):
    """
    A custom Gym environment for training an RL agent to trade BTC.
    Uses normalized observations and reward shaping from the Phipps strategy.
    """
    metadata = {"render_modes": ["human"]}

    # === REWARD TUNING CONSTANTS ===
    LIFE_PENALTY = -0.01          # Penalty per step of inactivity (the "bleeding out")
    RIBBON_KISS_BONUS = 2.0       # Multiplier for trades near EMA 50
    RIBBON_KISS_THRESHOLD = 0.003 # 0.3% distance from EMA 50 = "kiss"
    TRADE_COST = 0.0006           # Round-trip fee estimate (Coinbase One = ~0%)
    WIN_BONUS = 0.5               # Extra reward for profitable trade close
    LOSS_PENALTY = -0.3           # Extra penalty for losing trade close

    def __init__(self, df: pd.DataFrame, initial_balance: float = 10000.0,
                 max_steps: int = None, render_mode=None):
        super().__init__()
        self.render_mode = render_mode

        # Store the full dataframe with indicators pre-computed
        self.df = df.reset_index(drop=True)
        self.n_steps = len(self.df)
        self.max_steps = max_steps or self.n_steps

        self.initial_balance = initial_balance

        # Action: 0=HOLD, 1=BUY, 2=SELL
        self.action_space = spaces.Discrete(3)

        # Observation: 14 normalized features
        self.observation_space = spaces.Box(
            low=-np.inf, high=np.inf, shape=(14,), dtype=np.float32
        )

        # Internal state
        self._reset_state()

    def _reset_state(self):
        self.current_step = 0
        self.balance = self.initial_balance
        self.position = 0.0       # BTC held
        self.entry_price = 0.0
        self.steps_in_position = 0
        self.steps_idle = 0       # Steps with no position (for life penalty)
        self.total_trades = 0
        self.winning_trades = 0
        self.losing_trades = 0
        self.total_pnl = 0.0
        self.equity_curve = [self.initial_balance]

    def _get_row(self, idx=None):
        if idx is None:
            idx = self.current_step
        return self.df.iloc[idx]

    def _compute_observation(self) -> np.ndarray:
        row = self._get_row()
        close = row["Close"]

        # Safely get indicator values with fallbacks
        ema20 = row.get("EMA_20", close)
        ema50 = row.get("EMA_50", close)
        ema200 = row.get("EMA_200", close)
        rsi = row.get("rsi_value", 50.0)
        macd_hist = row.get("MACD_Hist", 0.0)
        atr = row.get("ATR", 0.0)
        volume = row.get("Volume", 0.0)
        vol_sma = row.get("Volume_SMA", max(volume, 1.0))
        adx = row.get("ADX", 25.0)
        chop = row.get("Choppiness", 50.0)

        # Handle NaN values
        for val_name in ['ema20', 'ema50', 'ema200', 'rsi', 'macd_hist', 'atr', 'adx', 'chop']:
            val = locals()[val_name]
            if pd.isna(val):
                if val_name in ['ema20', 'ema50', 'ema200']:
                    locals()[val_name] = close
                elif val_name == 'rsi':
                    rsi = 50.0
                elif val_name in ['macd_hist', 'atr']:
                    locals()[val_name] = 0.0
                elif val_name == 'adx':
                    adx = 25.0
                elif val_name == 'chop':
                    chop = 50.0

        # Re-assign after NaN handling
        ema20 = close if pd.isna(ema20) else ema20
        ema50 = close if pd.isna(ema50) else ema50
        ema200 = close if pd.isna(ema200) else ema200
        rsi = 50.0 if pd.isna(rsi) else rsi
        macd_hist = 0.0 if pd.isna(macd_hist) else macd_hist
        atr = 0.0 if pd.isna(atr) else atr
        adx = 25.0 if pd.isna(adx) else adx
        chop = 50.0 if pd.isna(chop) else chop
        vol_sma = max(vol_sma if not pd.isna(vol_sma) else 1.0, 1.0)

        # === FEATURE 1: NORMALIZATION (distance to SMA, not raw price) ===
        close_dist_sma20 = (close - ema20) / ema20 if ema20 > 0 else 0.0
        close_dist_sma50 = (close - ema50) / ema50 if ema50 > 0 else 0.0
        close_dist_ema200 = (close - ema200) / ema200 if ema200 > 0 else 0.0

        # Trend direction
        ema20_above_ema50 = 1.0 if ema20 > ema50 else -1.0

        # RSI normalized to [-1, 1]
        rsi_norm = (rsi - 50.0) / 50.0

        # MACD histogram normalized by ATR (scale-independent)
        macd_hist_norm = macd_hist / atr if atr > 0 else 0.0

        # ATR as percentage of price
        atr_pct = atr / close if close > 0 else 0.0

        # Volume ratio
        volume_ratio = volume / vol_sma if vol_sma > 0 else 1.0

        # ADX normalized [0, 1]
        adx_norm = min(adx / 100.0, 1.0)

        # Choppiness normalized [0, 1]
        chop_norm = min(chop / 100.0, 1.0)

        # === FEATURE 3: RIBBON KISS DETECTION ===
        ribbon_kiss = 1.0 if abs(close_dist_sma50) <= self.RIBBON_KISS_THRESHOLD else 0.0

        # Position info
        position_flag = 1.0 if self.position > 0 else 0.0
        unrealized_pnl = 0.0
        if self.position > 0 and self.entry_price > 0:
            unrealized_pnl = (close - self.entry_price) / self.entry_price

        time_in_pos = min(self.steps_in_position / 100.0, 1.0)

        obs = np.array([
            close_dist_sma20,
            close_dist_sma50,
            close_dist_ema200,
            ema20_above_ema50,
            rsi_norm,
            macd_hist_norm,
            atr_pct,
            volume_ratio,
            adx_norm,
            chop_norm,
            ribbon_kiss,
            position_flag,
            unrealized_pnl,
            time_in_pos,
        ], dtype=np.float32)

        # Clip extreme values
        obs = np.clip(obs, -10.0, 10.0)
        return obs

    def _is_ribbon_kiss(self) -> bool:
        """Check if current price is within kiss distance of EMA 50."""
        row = self._get_row()
        close = row["Close"]
        ema50 = row.get("EMA_50", close)
        if pd.isna(ema50) or ema50 <= 0:
            return False
        return abs((close - ema50) / ema50) <= self.RIBBON_KISS_THRESHOLD

    def reset(self, seed=None, options=None):
        super().reset(seed=seed)
        self._reset_state()

        # Random start point (leave room for at least 200 steps)
        max_start = max(0, self.n_steps - 200)
        if max_start > 50:
            self.current_step = self.np_random.integers(50, max_start)
        else:
            self.current_step = 50  # Need warm-up for indicators

        obs = self._compute_observation()
        info = {"balance": self.balance, "total_trades": 0}
        return obs, info

    def step(self, action):
        row = self._get_row()
        close = row["Close"]
        reward = 0.0
        info = {}

        # === EXECUTE ACTION ===
        if action == 1:  # BUY
            if self.position == 0:
                # Open long position (use 95% of balance for safety)
                buy_amount = (self.balance * 0.95) / close
                cost = buy_amount * close * self.TRADE_COST
                self.position = buy_amount
                self.entry_price = close
                self.balance -= cost
                self.steps_in_position = 0
                self.steps_idle = 0
                self.total_trades += 1

                # === FEATURE 3: RIBBON KISS BONUS ===
                if self._is_ribbon_kiss():
                    reward += self.RIBBON_KISS_BONUS
                    info["ribbon_kiss_entry"] = True

                reward -= self.TRADE_COST  # Small cost for entering

        elif action == 2:  # SELL
            if self.position > 0:
                # Close long position
                sell_value = self.position * close
                cost = sell_value * self.TRADE_COST
                pnl = (close - self.entry_price) / self.entry_price
                self.balance += sell_value - cost
                self.total_pnl += pnl

                # PnL-based reward
                reward += pnl * 10.0  # Scale PnL for reward signal

                # Win/loss bonus
                if pnl > 0:
                    reward += self.WIN_BONUS
                    self.winning_trades += 1
                else:
                    reward += self.LOSS_PENALTY
                    self.losing_trades += 1

                # === FEATURE 3: RIBBON KISS BONUS on profitable exit near EMA50 ===
                if self._is_ribbon_kiss() and pnl > 0:
                    reward += self.RIBBON_KISS_BONUS * 0.5

                self.position = 0.0
                self.entry_price = 0.0
                self.steps_in_position = 0

        else:  # HOLD (action == 0)
            if self.position > 0:
                # Holding a position — small reward based on unrealized PnL direction
                unrealized = (close - self.entry_price) / self.entry_price
                reward += unrealized * 0.1  # Gentle nudge
                self.steps_in_position += 1
            else:
                # === FEATURE 2: LIFE PENALTY (bleeding out while idle) ===
                self.steps_idle += 1
                reward += self.LIFE_PENALTY

        # Update equity
        equity = self.balance + (self.position * close)
        self.equity_curve.append(equity)

        # Advance step
        self.current_step += 1

        # Check termination
        terminated = False
        truncated = False

        if self.current_step >= self.n_steps - 1:
            truncated = True
            # Force close any open position at end
            if self.position > 0:
                pnl = (close - self.entry_price) / self.entry_price
                self.balance += self.position * close
                self.position = 0.0
                reward += pnl * 5.0

        if equity < self.initial_balance * 0.5:
            # Blown up — lost 50% of capital
            terminated = True
            reward -= 5.0

        obs = self._compute_observation() if not (terminated or truncated) else np.zeros(14, dtype=np.float32)

        info.update({
            "equity": equity,
            "balance": self.balance,
            "position": self.position,
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "total_pnl": self.total_pnl,
            "steps_idle": self.steps_idle,
        })

        return obs, reward, terminated, truncated, info

    def render(self):
        if self.render_mode == "human":
            row = self._get_row()
            equity = self.balance + (self.position * row["Close"])
            pos_str = f"{self.position:.6f} BTC @ {self.entry_price:.2f}" if self.position > 0 else "FLAT"
            print(f"Step {self.current_step} | Price: {row['Close']:.2f} | "
                  f"Equity: ${equity:.2f} | Pos: {pos_str} | "
                  f"Trades: {self.total_trades} | Idle: {self.steps_idle}")
