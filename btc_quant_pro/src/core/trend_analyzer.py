import pandas as pd
import numpy as np

class TrendAnalyzer:
    """Identifies swing points and calculates trendline coordinates."""

    @staticmethod
    def find_swings(df: pd.DataFrame, window: int = 5) -> pd.DataFrame:
        df = df.copy()
        # A swing high is the highest point in a window of 2*window + 1
        df['is_swing_high'] = df['High'] == df['High'].rolling(window=window*2+1, center=True).max()
        # A swing low is the lowest point in a window of 2*window + 1
        df['is_swing_low'] = df['Low'] == df['Low'].rolling(window=window*2+1, center=True).min()
        return df

    @staticmethod
    def get_trendlines(df: pd.DataFrame, window: int = 5):
        df = TrendAnalyzer.find_swings(df, window)
        
        highs = df[df['is_swing_high'] == True].copy()
        lows = df[df['is_swing_low'] == True].copy()
        
        lines = {
            'bullish_support': [], # Connecting Higher Lows
            'bullish_resistance': [], # Connecting Higher Highs
            'bearish_resistance': [], # Connecting Lower Highs
            'bearish_support': []  # Connecting Lower Lows
        }

        # 1. Bullish Support (Higher Lows)
        if len(lows) >= 2:
            for i in range(1, len(lows)):
                if lows['Low'].iloc[i] > lows['Low'].iloc[i-1]:
                    lines['bullish_support'].append((lows.index[i-1], lows['Low'].iloc[i-1], 
                                                   lows.index[i], lows['Low'].iloc[i]))

        # 2. Bullish Resistance (Higher Highs)
        if len(highs) >= 2:
            for i in range(1, len(highs)):
                if highs['High'].iloc[i] > highs['High'].iloc[i-1]:
                    lines['bullish_resistance'].append((highs.index[i-1], highs['High'].iloc[i-1], 
                                                      highs.index[i], highs['High'].iloc[i]))

        # 3. Bearish Resistance (Lower Highs)
        if len(highs) >= 2:
            for i in range(1, len(highs)):
                if highs['High'].iloc[i] < highs['High'].iloc[i-1]:
                    lines['bearish_resistance'].append((highs.index[i-1], highs['High'].iloc[i-1], 
                                                      highs.index[i], highs['High'].iloc[i]))

        # 4. Bearish Support (Lower Lows)
        if len(lows) >= 2:
            for i in range(1, len(lows)):
                if lows['Low'].iloc[i] < lows['Low'].iloc[i-1]:
                    lines['bearish_support'].append((lows.index[i-1], lows['Low'].iloc[i-1], 
                                                   lows.index[i], lows['Low'].iloc[i]))

        return lines
