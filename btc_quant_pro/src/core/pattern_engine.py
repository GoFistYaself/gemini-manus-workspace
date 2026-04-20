import pandas as pd
import numpy as np
import logging

logger = logging.getLogger(__name__)

class PatternEngine:
    """The 'Learning Arm' that identifies candlestick formations and structural patterns."""

    def __init__(self):
        # knowledge_base stores: {pattern_name: {'success_rate': float, 'sample_size': int, 'reliability': float}}
        self.knowledge_base = {} 

    def identify_all_patterns(self, df: pd.DataFrame) -> pd.DataFrame:
        """Applies recognition logic for 1-3 candle and structural patterns."""
        df = df.copy()
        
        # Helper metrics
        df["body"] = df["Close"] - df["Open"]
        df["abs_body"] = df["body"].abs()
        df["range"] = df["High"] - df["Low"]
        df["upper_wick"] = df["High"] - df[["Open", "Close"]].max(axis=1)
        df["lower_wick"] = df[["Open", "Close"]].min(axis=1) - df["Low"]
        df["avg_body"] = df["abs_body"].rolling(window=20).mean()

        # --- 1-Candle Patterns ---
        # Hammer: Small body at top, long lower wick
        df["p_hammer"] = (df["lower_wick"] > df["abs_body"] * 2) & (df["upper_wick"] < df["abs_body"] * 0.5)
        # Shooting Star: Small body at bottom, long upper wick
        df["p_shooting_star"] = (df["upper_wick"] > df["abs_body"] * 2) & (df["lower_wick"] < df["abs_body"] * 0.5)
        # Doji: Opening and closing are almost the same
        df["p_doji"] = df["abs_body"] <= (df["range"] * 0.1)

        # --- 2-Candle Patterns ---
        # Bullish Engulfing
        df["p_bull_engulfing"] = (df["body"].shift(1) < 0) & (df["body"] > 0) & \
                                 (df["Open"] < df["Close"].shift(1)) & (df["Close"] > df["Open"].shift(1))
        # Bearish Engulfing
        df["p_bear_engulfing"] = (df["body"].shift(1) > 0) & (df["body"] < 0) & \
                                 (df["Open"] > df["Close"].shift(1)) & (df["Close"] < df["Open"].shift(1))

        # --- 3-Candle Patterns ---
        # Morning Star (Simplified)
        df["p_morning_star"] = (df["body"].shift(2) < 0) & (df["p_doji"].shift(1)) & (df["body"] > 0) & \
                               (df["Close"] > df["Open"].shift(2).iloc[0] if len(df) > 2 else False)

        # Three White Soldiers (3 consecutive green candles, each closing higher)
        df["p_three_white_soldiers"] = (df["body"] > 0) & (df["body"].shift(1) > 0) & (df["body"].shift(2) > 0) & \
                                       (df["Close"] > df["Close"].shift(1)) & (df["Close"].shift(1) > df["Close"].shift(2)) & \
                                       (df["Open"] > df["Open"].shift(1)) & (df["Open"].shift(1) > df["Open"].shift(2))

        # Three Black Crows (3 consecutive red candles, each closing lower)
        df["p_three_black_crows"] = (df["body"] < 0) & (df["body"].shift(1) < 0) & (df["body"].shift(2) < 0) & \
                                    (df["Close"] < df["Close"].shift(1)) & (df["Close"].shift(1) < df["Close"].shift(2)) & \
                                    (df["Open"] < df["Open"].shift(1)) & (df["Open"].shift(1) < df["Open"].shift(2))

        # --- Complex Chart Patterns (Flags, Wedges) ---
        df = self._detect_complex_patterns(df)

        return df

    def _detect_complex_patterns(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Detects larger formations: Bull/Bear Flags, Falling/Ascending Wedges.
        Uses a sliding window approach with linear regression for slope detection.
        Optimized with NumPy vectorization to eliminate 100% CPU load.
        """
        import numpy as np
        xp = np
        has_gpu = False

        df = df.copy()
        # Initialize columns
        df["p_bull_flag"] = False
        df["p_bear_flag"] = False
        df["p_falling_wedge"] = False
        df["p_ascending_wedge"] = False
        
        # Parameters
        window_size = 15     # Lookback for pattern (Pole + Consolidation)
        pole_size = 5        # First 5 bars for Pole
        consol_size = 10     # Last 10 bars for Consolidation
        
        if len(df) < window_size:
            return df
            
        N = len(df)
        
        close_vals = df["Close"].values
        high_vals = df["High"].values
        low_vals = df["Low"].values
            
        # 1. Vectorized Pole Detection
        pole_start = xp.zeros(N)
        pole_end = xp.zeros(N)
        
        pole_start[window_size:] = close_vals[:-window_size]
        pole_end[window_size:] = close_vals[window_size - consol_size:-consol_size]
        
        pole_start = xp.where(pole_start == 0, 1e-9, pole_start)
        pole_change = xp.zeros(N)
        pole_change[window_size:] = (pole_end[window_size:] - pole_start[window_size:]) / pole_start[window_size:]
        
        is_bull_pole = pole_change > 0.015
        is_bear_pole = pole_change < -0.015
        
        # 2. Vectorized Rolling Linear Regression
        w = consol_size + 1
        x = xp.arange(w, dtype=xp.float32)
        sum_x = xp.sum(x)
        sum_x2 = xp.sum(x**2)
        denominator = w * sum_x2 - sum_x**2
        
        shape = (N - w + 1, w)
        strides = (high_vals.strides[0], high_vals.strides[0])
        
        from numpy.lib.stride_tricks import as_strided
            
        high_windows = as_strided(high_vals, shape=shape, strides=strides)
        low_windows = as_strided(low_vals, shape=shape, strides=strides)
        
        sum_y_high = xp.sum(high_windows, axis=1)
        sum_xy_high = xp.sum(high_windows * x, axis=1)
        
        sum_y_low = xp.sum(low_windows, axis=1)
        sum_xy_low = xp.sum(low_windows * x, axis=1)
        
        slope_high = (w * sum_xy_high - sum_x * sum_y_high) / denominator
        slope_low = (w * sum_xy_low - sum_x * sum_y_low) / denominator
        
        pad = xp.zeros(w - 1)
        slope_high = xp.concatenate([pad, slope_high])
        slope_low = xp.concatenate([pad, slope_low])
        
        valid_mask = xp.arange(N) >= window_size
        safe_close = xp.where(close_vals == 0, 1e-9, close_vals)
        
        slope_high_norm = (slope_high / safe_close) * 100
        slope_low_norm = (slope_low / safe_close) * 100
        
        is_converging = slope_high < slope_low
        is_parallel = xp.abs(slope_high - slope_low) < 0.05
        
        # 3. Compute Booleans
        bull_flag_cond = valid_mask & is_bull_pole & (slope_high_norm < -0.05) & (slope_low_norm < -0.05) & is_parallel
        falling_wedge_cond = valid_mask & is_bull_pole & (slope_high_norm < -0.05) & (slope_low_norm < -0.05) & is_converging
        
        bear_flag_cond = valid_mask & is_bear_pole & (slope_high_norm > 0.05) & (slope_low_norm > 0.05) & is_parallel
        ascending_wedge_cond = valid_mask & is_bear_pole & (slope_high_norm > 0.05) & (slope_low_norm > 0.05) & (slope_low > slope_high)
        
        df.loc[bull_flag_cond, "p_bull_flag"] = True
        df.loc[falling_wedge_cond, "p_falling_wedge"] = True
        df.loc[bear_flag_cond, "p_bear_flag"] = True
        df.loc[ascending_wedge_cond, "p_ascending_wedge"] = True

        return df

    def learn_performance(self, df: pd.DataFrame, target_window: int = 5):
        """
        Analyzes the historical success of each pattern.
        A pattern is 'successful' if price moves > 1% in the expected direction within target_window.
        """
        df = self.identify_all_patterns(df)
        patterns = [
            "p_hammer", "p_shooting_star", "p_doji", 
            "p_bull_engulfing", "p_bear_engulfing", 
            "p_morning_star", "p_three_white_soldiers", "p_three_black_crows",
            "p_bull_flag", "p_bear_flag", "p_falling_wedge", "p_ascending_wedge"
        ]
        
        for p in patterns:
            occurrences = df[df[p] == True]
            sample_size = len(occurrences)
            
            if sample_size == 0:
                self.knowledge_base[p] = {"success_rate": 0.5, "sample_size": 0, "reliability": 0.0}
                continue
            
            successes = 0
            for idx in occurrences.index:
                # Find the forward return
                try:
                    current_price = df.loc[idx, "Close"]
                    future_slice = df.loc[idx:].iloc[1:target_window+1] # Look ahead
                    
                    if future_slice.empty: 
                        continue

                    future_max = future_slice["High"].max()
                    future_min = future_slice["Low"].min()
                    
                    # Expected direction
                    # Bullish Patterns
                    if p in ["p_hammer", "p_bull_engulfing", "p_morning_star", "p_three_white_soldiers", "p_bull_flag", "p_falling_wedge"]:
                        # Success: Price goes up > 0.5% (lowered threshold for higher freq) without stopping out
                        if (future_max - current_price) / current_price > 0.005:
                            successes += 1
                    # Bearish Patterns
                    else: 
                        if (current_price - future_min) / current_price > 0.005:
                            successes += 1
                except Exception as e:
                    continue
            
            success_rate = successes / sample_size if sample_size > 0 else 0
            
            # Simple reliability score: Rate * Log(Sample Size)
            # This favors patterns that work often over many samples.
            reliability = (success_rate - 0.5) * np.log1p(sample_size)
            
            self.knowledge_base[p] = {
                "success_rate": success_rate, 
                "sample_size": sample_size,
                "reliability": reliability
            }
            
            logger.info(f"Learned {p}: Rate {success_rate:.1%} (N={sample_size}) -> Reliability: {reliability:.2f}")

    def get_pattern_score(self, row) -> float:
        """Returns a weighted score based on active patterns and learned knowledge."""
        score = 0
        for p, data in self.knowledge_base.items():
            if row.get(p) == True:
                # Use the reliability score directly
                score += data["reliability"] * 5 # Scale up for signal engine
        return score
