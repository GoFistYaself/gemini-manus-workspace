import pandas as pd
import numpy as np
from src.core.trend_analyzer import TrendAnalyzer

class AdvancedPatterns:
    """Detects Indicator Divergences and Market Structure Patterns (Flags, Wedges)."""

    @staticmethod
    def detect_divergence(df: pd.DataFrame, indicator_col: str, window: int = 5) -> pd.Series:
        """
        Detects Bullish and Bearish Divergences.
        Returns: 1 for Bullish, -1 for Bearish, 0 for None.
        """
        df = TrendAnalyzer.find_swings(df, window)
        signals = pd.Series(0, index=df.index)
        
        # Get swing points
        highs = df[df['is_swing_high'] == True]
        lows = df[df['is_swing_low'] == True]

        # 1. Bullish Divergence (Price Lower Low, Indicator Higher Low)
        if len(lows) >= 2:
            for i in range(1, len(lows)):
                price_ll = lows['Low'].iloc[i] < lows['Low'].iloc[i-1]
                ind_hl = lows[indicator_col].iloc[i] > lows[indicator_col].iloc[i-1]
                if price_ll and ind_hl:
                    signals.loc[lows.index[i]] = 1

        # 2. Bearish Divergence (Price Higher High, Indicator Lower High)
        if len(highs) >= 2:
            for i in range(1, len(highs)):
                price_hh = highs['High'].iloc[i] > highs['High'].iloc[i-1]
                ind_lh = highs[indicator_col].iloc[i] < highs[indicator_col].iloc[i-1]
                if price_hh and ind_lh:
                    signals.loc[highs.index[i]] = -1
                    
        return signals

    @staticmethod
    def get_fibonacci_retracements(df: pd.DataFrame, window: int = 50) -> dict:
        """
        Identifies the major Swing High and Swing Low in the recent window
        and calculates Fibonacci Retracement levels (0.382, 0.5, 0.618).
        """
        # Ensure we have enough data
        if len(df) < 10:
             return {'trend': 'NEUTRAL', 'levels': {0.382:0, 0.5:0, 0.618:0}, 'high': 0, 'low': 0}

        # Focus on recent window
        actual_window = min(len(df), window)
        recent_df = df.iloc[-actual_window:]
        
        if recent_df.empty:
             return {'trend': 'NEUTRAL', 'levels': {0.382:0, 0.5:0, 0.618:0}, 'high': 0, 'low': 0}
             
        # Identify Max High and Min Low
        max_idx = recent_df['High'].idxmax()
        min_idx = recent_df['Low'].idxmin()
        
        # Normalize indices to ensure comparison works (Handles TZ-aware vs Naive)
        def normalize_idx(idx):
            if hasattr(idx, 'tz_localize') and idx.tz is not None:
                return idx.tz_localize(None)
            return idx

        m_idx_norm = normalize_idx(max_idx)
        n_idx_norm = normalize_idx(min_idx)

        high_price = recent_df.loc[max_idx, 'High']
        low_price = recent_df.loc[min_idx, 'Low']
        
        levels = {}
        trend = "NEUTRAL"
        
        # Determine Direction
        # If Low occurred BEFORE High -> UPTREND (Measure Pullback Down)
        if n_idx_norm < m_idx_norm:
            trend = "UP"
            diff = high_price - low_price
            levels[0.382] = high_price - (diff * 0.382)
            levels[0.5] = high_price - (diff * 0.5)
            levels[0.618] = high_price - (diff * 0.618) # Golden Pocket
            levels['target'] = high_price # Target is retesting high
            
        # If High occurred BEFORE Low -> DOWNTREND (Measure Pullback Up)
        elif m_idx_norm < n_idx_norm:
            trend = "DOWN"
            diff = high_price - low_price
            levels[0.382] = low_price + (diff * 0.382)
            levels[0.5] = low_price + (diff * 0.5)
            levels[0.618] = low_price + (diff * 0.618) # Golden Pocket
            levels['target'] = low_price # Target is retesting low
            
        return {'trend': trend, 'levels': levels, 'high': high_price, 'low': low_price}

    @staticmethod
    def detect_market_structure(df: pd.DataFrame, window: int = 10) -> pd.Series:
        """
        Detects Flags and Wedges using Trendline Slopes.
        Returns: 1 for Bullish Breakout Potential, -1 for Bearish.
        """
        signals = pd.Series(0, index=df.index)
        lines = TrendAnalyzer.get_trendlines(df, window)
        
        # Simple slope calculation for the most recent lines
        def get_slope(line):
            # line: (t1, p1, t2, p2)
            # We treat time as index integer for slope
            return (line[3] - line[1]) / 10 # Approximation

        # 1. Bullish Flag / Falling Wedge
        # Criteria: Both resistance and support lines are sloping DOWNWARDS (Converging or Parallel)
        # and price is near the upper resistance.
        if lines['bearish_resistance'] and lines['bearish_support']:
            last_res = lines['bearish_resistance'][-1]
            last_sup = lines['bearish_support'][-1]
            
            slope_res = get_slope(last_res)
            slope_sup = get_slope(last_sup)
            
            # Falling Wedge (Converging Down)
            if slope_res < 0 and slope_sup < 0 and slope_res > slope_sup:
                # Potential Bullish Breakout
                signals.loc[df.index[-1]] = 1
                
        # 2. Bearish Flag / Rising Wedge
        # Criteria: Both lines sloping UPWARDS
        if lines['bullish_resistance'] and lines['bullish_support']:
            last_res = lines['bullish_resistance'][-1]
            last_sup = lines['bullish_support'][-1]
            
            slope_res = get_slope(last_res)
            slope_sup = get_slope(last_sup)
            
            # Rising Wedge (Converging Up)
            if slope_res > 0 and slope_sup > 0 and slope_res < slope_sup:
                # Potential Bearish Breakout
                signals.loc[df.index[-1]] = -1

        return signals

    @staticmethod
    def detect_fib_pivots(df, window=24):
        """Identifies local highs and lows for Fibonacci calculation."""
        # Use a trailing window for live data
        df = df.copy()
        df['Local_Max'] = df['High'].rolling(window=window).max()
        df['Local_Min'] = df['Low'].rolling(window=window).min()
        df['is_high'] = df['High'] == df['Local_Max']
        df['is_low'] = df['Low'] == df['Local_Min']
        return df

    @staticmethod
    def get_fib_targets(df, current_idx=None):
        """Calculates 1.618 extension target based on latest A-B-C structure."""
        if current_idx is None:
            current_idx = len(df) - 1
            
        # Ensure we have enough rows
        if current_idx < 1: return None
        lookback = df.iloc[:current_idx+1]
        
        # 1. Point B (Recent High)
        highs = lookback[lookback['is_high']]
        if len(highs) < 1: return None
        b_idx = highs.index[-1]
        b_val = highs.loc[b_idx, 'High']
        
        # 2. Point A (Low before B)
        lows_before_b = lookback.loc[:b_idx]
        lows_before_b = lows_before_b[lows_before_b['is_low']]
        if len(lows_before_b) < 1: return None
        a_val = lows_before_b.iloc[-1]['Low']
        
        # 3. Point C (Retracement Low)
        retracement_zone = lookback.loc[b_idx:]
        c_val = retracement_zone['Low'].min()
        
        if c_val <= a_val: return None
        
        impulse = b_val - a_val
        return {
            "target_161": c_val + (impulse * 1.618),
            "target_100": c_val + impulse,
            "c_val": c_val
        }
