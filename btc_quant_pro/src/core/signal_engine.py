import pandas as pd
import numpy as np

from src.core.advanced_patterns import AdvancedPatterns
from src.core.pattern_engine import PatternEngine

class SignalEngine:
    """Generates specialized signals with Learned Pattern recognition."""
    
    def __init__(self, interval='1h', nearness_threshold=0.005, volume_multiplier=1.0, pattern_engine=None):
        self.interval = interval
        self.threshold = nearness_threshold
        self.vol_mult = volume_multiplier
        self.pe = pattern_engine or PatternEngine()

    def generate_signals(self, df: pd.DataFrame, last_only=False) -> pd.DataFrame:
        # 1. Identify all patterns first
        df = self.pe.identify_all_patterns(df)
        
        df['Signal'] = 0
        df['P_Score'] = 0.0 # Initialize P_Score column

        # Global Conditions
        df['ema_trend_bullish'] = pd.to_numeric(df['EMA_50'], errors='coerce') > pd.to_numeric(df['EMA_200'], errors='coerce')
        df['ema_trend_bearish'] = pd.to_numeric(df['EMA_50'], errors='coerce') < pd.to_numeric(df['EMA_200'], errors='coerce')
        df['vol_confirm'] = (df['Volume'] > df['Volume_SMA'] * self.vol_mult)
        
        # Advanced Pattern Pre-calculation
        df['rsi_div'] = AdvancedPatterns.detect_divergence(df, 'rsi_value')
        df['macd_div'] = AdvancedPatterns.detect_divergence(df, 'MACD')
        df['mkt_struct'] = AdvancedPatterns.detect_market_structure(df)
        
        if self.interval == '1h':
            self._apply_1h_trend_logic(df, last_only=last_only)
        else:
            self._apply_15m_scalp_logic(df, last_only=last_only)
            
        return df

    def _is_near(self, price, level):
        return np.abs(price - level) <= self.threshold * level

    def _apply_1h_trend_logic(self, df, last_only=False):
        """1H: Trend Follower + Learned Reversals."""
        start_idx = 50
        if last_only:
            start_idx = len(df) - 1

        for i in range(start_idx, len(df)):
            row = df.iloc[i]
            p_score = self.pe.get_pattern_score(row)
            df.at[df.index[i], 'P_Score'] = p_score
            
            # Standard Trend Entry
            macd_bullish = (row['MACD_Hist'] > 0)
            regime = row.get('Regime', 'NEUTRAL')
            
            trade_allowed = regime != 'CRISIS'
            # Ensure indicators are not None/NaN before comparison
            ema_valid = not (pd.isna(row['EMA_20']) or pd.isna(row['EMA_50']))
            rsi_valid = not pd.isna(row['rsi_value'])
            
            trend_entry = False
            if ema_valid and rsi_valid:
                trend_entry = (row['EMA_20'] > row['EMA_50']) and macd_bullish and (row['rsi_value'] > 45)
            
            if regime == "CRISIS":
                continue

            # Relaxed 1h standard entry: EITHER vol_confirm OR p_score > 0
            if (trend_entry and row["vol_confirm"] and p_score is not None and p_score >= 0) and trade_allowed:
                df.at[df.index[i], 'Signal'] = 1
            elif (ema_valid and row["EMA_20"] < row["EMA_50"] and row["vol_confirm"] and p_score is not None and p_score < 0):
                df.at[df.index[i], 'Signal'] = -1

            # SNIPER MODE (Ultra-high reliability patterns)
            if p_score is not None and p_score >= 0.5:
                df.at[df.index[i], 'Signal'] = 1
            elif p_score is not None and p_score <= -0.5:
                df.at[df.index[i], 'Signal'] = -1

            # Fallback signals: require at least 2 independent confirmations
            if i > 0:
                prev_ema_valid = not (pd.isna(df['EMA_20'].iloc[i-1]) or pd.isna(df['EMA_50'].iloc[i-1]))
                ema_cross_bullish = ema_valid and prev_ema_valid and (row['EMA_20'] > row['EMA_50']) and (df['EMA_20'].iloc[i-1] <= df['EMA_50'].iloc[i-1])
                ema_cross_bearish = ema_valid and prev_ema_valid and (row['EMA_20'] < row['EMA_50']) and (df['EMA_20'].iloc[i-1] >= df['EMA_50'].iloc[i-1])
                rsi_extreme_buy = row['rsi_value'] < 30
                rsi_extreme_sell = row['rsi_value'] > 70
                macd_hist_cross_up = (row['MACD_Hist'] > 0) and (df['MACD_Hist'].iloc[i-1] <= 0)
                macd_hist_cross_down = (row['MACD_Hist'] < 0) and (df['MACD_Hist'].iloc[i-1] >= 0)

                bull_confirms = sum([ema_cross_bullish, rsi_extreme_buy, macd_hist_cross_up])
                bear_confirms = sum([ema_cross_bearish, rsi_extreme_sell, macd_hist_cross_down])

                if bull_confirms >= 2 and df.at[df.index[i], 'Signal'] == 0:
                    df.at[df.index[i], 'Signal'] = 1
                elif bear_confirms >= 2 and df.at[df.index[i], 'Signal'] == 0:
                    df.at[df.index[i], 'Signal'] = -1

    def _apply_15m_scalp_logic(self, df, last_only=False):
        """15M: High Frequency Scalping - OPTIMIZED FOR COINBASE ONE (Zero Fees)."""
        start_idx = 0
        if last_only:
            start_idx = len(df) - 1

        # COINBASE ONE: Fee is 0.0%, so we remove the fee shield.
        FEE_SHIELD_PCT = 0.000 

        for i in range(start_idx, len(df)):
            row = df.iloc[i]
            p_score = self.pe.get_pattern_score(row)
            df.at[df.index[i], 'P_Score'] = p_score
            
            # --- NEW: SNIPER OVERRIDE (v3.9 - Coinbase One Edition) ---
            # Lower threshold (0.1) because fees are zero. Catch the move earlier.
            if abs(p_score) >= 0.1:
                if p_score > 0:
                    df.at[df.index[i], 'Signal'] = 1
                else:
                    df.at[df.index[i], 'Signal'] = -1
                continue # Skip standard logic

            atr = row.get('ATR', 0.0)
            price = row['Close']
            tp_dist = atr * 1.5
            reward_pct = tp_dist / price if price > 0 else 0
            
            if reward_pct >= FEE_SHIELD_PCT:
                if p_score > 0.05:
                    df.at[df.index[i], 'Signal'] = 1
                elif p_score < -0.05:
                    df.at[df.index[i], 'Signal'] = -1
            else:
                df.at[df.index[i], 'Signal'] = 0
