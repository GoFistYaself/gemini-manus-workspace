"""
RL Signal Engine - Integrates the trained Phipps RL agent into the live trading bot.

This module wraps the trained PPO model and provides a simple interface:
    signal = rl_engine.get_signal(df, position_info)

Returns: 1 (BUY), -1 (SELL), or 0 (HOLD)

The RL agent's signal is used as one vote in the multi-timeframe voting system,
weighted alongside the existing pattern/signal engines.
"""

import os
import logging
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Lazy import SB3
_PPO = None


def _load_ppo():
    global _PPO
    if _PPO is None:
        try:
            from stable_baselines3 import PPO
            _PPO = PPO
        except ImportError:
            logger.error("stable-baselines3 not installed. RL signals disabled.")
    return _PPO


class RLSignalEngine:
    """
    Wraps a trained PPO agent to generate trading signals.
    Designed to plug into the existing AITradingBot voting system.
    """

    # Must match PhippsTradingEnv constants
    RIBBON_KISS_THRESHOLD = 0.003

    def __init__(self, model_path: str = None):
        self.model = None
        self.model_path = model_path or os.path.join(
            os.path.dirname(__file__), "..", "..", "models", "phipps_agent.zip"
        )
        self._load_model()

    def _load_model(self):
        """Load the trained PPO model."""
        PPO = _load_ppo()
        if PPO is None:
            return

        if not os.path.exists(self.model_path):
            logger.warning(f"RL model not found at {self.model_path}. Run train_agent.py first.")
            return

        try:
            self.model = PPO.load(self.model_path)
            logger.info(f"RL Agent loaded from {self.model_path}")
        except Exception as e:
            logger.error(f"Failed to load RL model: {e}")
            self.model = None

    def is_ready(self) -> bool:
        """Check if the RL model is loaded and ready."""
        return self.model is not None

    def _build_observation(self, row: dict, position_size: float = 0.0,
                           entry_price: float = 0.0, steps_in_pos: int = 0) -> np.ndarray:
        """
        Build the 14-feature observation vector from a data row.
        Must match PhippsTradingEnv._compute_observation() exactly.
        """
        close = float(row.get("Close", 0))
        if close <= 0:
            return np.zeros(14, dtype=np.float32)

        ema20 = float(row.get("EMA_20", close))
        ema50 = float(row.get("EMA_50", close))
        ema200 = float(row.get("EMA_200", close))
        rsi = float(row.get("rsi_value", 50.0))
        macd_hist = float(row.get("MACD_Hist", 0.0))
        atr = float(row.get("ATR", 0.0))
        volume = float(row.get("Volume", 0.0))
        vol_sma = float(row.get("Volume_SMA", max(volume, 1.0)))
        adx = float(row.get("ADX", 25.0))
        chop = float(row.get("Choppiness", 50.0))

        # Handle NaN
        if pd.isna(ema20): ema20 = close
        if pd.isna(ema50): ema50 = close
        if pd.isna(ema200): ema200 = close
        if pd.isna(rsi): rsi = 50.0
        if pd.isna(macd_hist): macd_hist = 0.0
        if pd.isna(atr): atr = 0.0
        if pd.isna(adx): adx = 25.0
        if pd.isna(chop): chop = 50.0
        if pd.isna(vol_sma) or vol_sma <= 0: vol_sma = 1.0

        # Normalized features
        close_dist_sma20 = (close - ema20) / ema20 if ema20 > 0 else 0.0
        close_dist_sma50 = (close - ema50) / ema50 if ema50 > 0 else 0.0
        close_dist_ema200 = (close - ema200) / ema200 if ema200 > 0 else 0.0
        ema20_above_ema50 = 1.0 if ema20 > ema50 else -1.0
        rsi_norm = (rsi - 50.0) / 50.0
        macd_hist_norm = macd_hist / atr if atr > 0 else 0.0
        atr_pct = atr / close if close > 0 else 0.0
        volume_ratio = volume / vol_sma if vol_sma > 0 else 1.0
        adx_norm = min(adx / 100.0, 1.0)
        chop_norm = min(chop / 100.0, 1.0)
        ribbon_kiss = 1.0 if abs(close_dist_sma50) <= self.RIBBON_KISS_THRESHOLD else 0.0

        # Position info
        position_flag = 1.0 if position_size > 0 else 0.0
        unrealized_pnl = 0.0
        if position_size > 0 and entry_price > 0:
            unrealized_pnl = (close - entry_price) / entry_price
        time_in_pos = min(steps_in_pos / 100.0, 1.0)

        obs = np.array([
            close_dist_sma20, close_dist_sma50, close_dist_ema200,
            ema20_above_ema50, rsi_norm, macd_hist_norm, atr_pct,
            volume_ratio, adx_norm, chop_norm, ribbon_kiss,
            position_flag, unrealized_pnl, time_in_pos,
        ], dtype=np.float32)

        return np.clip(obs, -10.0, 10.0)

    def get_signal(self, row: dict, position_size: float = 0.0,
                   entry_price: float = 0.0, steps_in_pos: int = 0) -> int:
        """
        Get a trading signal from the RL agent.

        Args:
            row: Dictionary of current candle data with indicators
            position_size: Current BTC position size (0 = flat)
            entry_price: Entry price of current position
            steps_in_pos: Number of ticks in current position

        Returns:
            1 = BUY, -1 = SELL, 0 = HOLD
        """
        if not self.is_ready():
            return 0  # No signal if model not loaded

        obs = self._build_observation(row, position_size, entry_price, steps_in_pos)

        try:
            action, _ = self.model.predict(obs, deterministic=True)
            action = int(action)

            # Map: 0=HOLD, 1=BUY, 2=SELL
            if action == 1:
                return 1   # BUY
            elif action == 2:
                return -1  # SELL
            else:
                return 0   # HOLD

        except Exception as e:
            logger.error(f"RL prediction error: {e}")
            return 0

    def get_signal_with_confidence(self, row: dict, position_size: float = 0.0,
                                    entry_price: float = 0.0,
                                    steps_in_pos: int = 0) -> tuple:
        """
        Get signal with action probabilities for confidence weighting.

        Returns:
            (signal, confidence) where confidence is 0.0-1.0
        """
        if not self.is_ready():
            return 0, 0.0

        obs = self._build_observation(row, position_size, entry_price, steps_in_pos)

        try:
            # Get action distribution
            action, _ = self.model.predict(obs, deterministic=True)
            action = int(action)

            # Get action probabilities
            obs_tensor = self.model.policy.obs_to_tensor(obs.reshape(1, -1))[0]
            dist = self.model.policy.get_distribution(obs_tensor)
            probs = dist.distribution.probs.detach().cpu().numpy()[0]

            confidence = float(probs[action])

            if action == 1:
                return 1, confidence
            elif action == 2:
                return -1, confidence
            else:
                return 0, confidence

        except Exception as e:
            logger.error(f"RL confidence prediction error: {e}")
            return 0, 0.0
