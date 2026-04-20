import pandas as pd
import numpy as np
import pandas_ta as ta

class IndicatorCalculator:
    """
    Calculates all technical indicators used by the strategy.
    Optimized for high-performance execution using pandas_ta (C-accelerated).
    """

    @staticmethod
    def apply_indicators(df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        
        # --- Standard Moving Averages ---
        df['EMA_20'] = ta.ema(df['Close'], length=20)
        df['EMA_50'] = ta.ema(df['Close'], length=50)
        df['EMA_200'] = ta.ema(df['Close'], length=200)

        # --- RSI (Relative Strength Index) ---
        # length 18 as per your original manual calculation
        rsi_df = ta.rsi(df['Close'], length=18)
        df['rsi_value'] = rsi_df
        df['rsi_ma'] = ta.ema(df['rsi_value'], length=10)
        
        # --- ATR (Average True Range) ---
        df['ATR'] = ta.atr(df['High'], df['Low'], df['Close'], length=14)

        # --- ADX (Average Directional Index) ---
        df['ADX'] = np.nan
        df['DMP'] = np.nan
        df['DMN'] = np.nan
        adx_df = ta.adx(df['High'], df['Low'], df['Close'], length=14)
        if adx_df is not None:
            df['ADX'] = adx_df['ADX_14']
            df['DMP'] = adx_df['DMP_14']
            df['DMN'] = adx_df['DMN_14']

        # --- MACD (Moving Average Convergence Divergence) ---
        df['MACD'] = np.nan
        df['MACD_Signal'] = np.nan
        df['MACD_Hist'] = np.nan
        macd_df = ta.macd(df['Close'], fast=12, slow=26, signal=9)
        if macd_df is not None:
            df['MACD'] = macd_df['MACD_12_26_9']
            df['MACD_Signal'] = macd_df['MACDs_12_26_9']
            df['MACD_Hist'] = macd_df['MACDh_12_26_9']

        # --- Volume Indicators ---
        df['Volume_SMA'] = ta.sma(df['Volume'], length=20)
        df['Vol_Surge'] = df['Volume'] > (df['Volume_SMA'] * 1.5)

        # --- Market Regime Detection ---
        df['ATR_MA'] = ta.sma(df['ATR'], length=50)
        df['Regime'] = "NEUTRAL"
        df.loc[df['ADX'] > 20, 'Regime'] = "TRENDING"
        df.loc[df['ADX'] <= 20, 'Regime'] = "RANGING"
        df.loc[df['ATR'] > df['ATR_MA'] * 3.0, 'Regime'] = "CRISIS"

        # --- Optimized Indicators (v3.3+) ---
        # 1. Choppiness Index
        df['Choppiness'] = ta.chop(df['High'], df['Low'], df['Close'], length=14)

        # 2. Volume Price Trend (VPT) - Manual remains efficient but we'll use clean vector logic
        df['VPT'] = (df['Volume'] * (df['Close'].pct_change())).fillna(0).cumsum()
        df['VPT_SMA'] = ta.sma(df['VPT'], length=20)

        # --- Ray-Pivot Scalper Indicators (v3.5) ---
        # Using 96 periods for 15m (24h) rolling daily estimates
        df['Prev_Day_High'] = df['High'].shift(1).rolling(window=96).max()
        df['Prev_Day_Low'] = df['Low'].shift(1).rolling(window=96).min()
        df['Prev_Day_Close'] = df['Close'].shift(96)
        
        df['Pivot'] = (df['Prev_Day_High'] + df['Prev_Day_Low'] + df['Prev_Day_Close']) / 3
        df['R1_Pivot'] = (2 * df['Pivot']) - df['Prev_Day_Low']
        df['S1_Pivot'] = (2 * df['Pivot']) - df['Prev_Day_High']
        
        # --- Fibonacci Pivot Levels (Legacy Support) ---
        df['R1'] = df['Pivot'] + (df['Pivot'] - df['Prev_Day_Low'])
        df['R2'] = df['Pivot'] + (df['Prev_Day_High'] - df['Prev_Day_Low'])
        df['S1'] = df['Pivot'] - (df['Prev_Day_High'] - df['Pivot'])
        df['S2'] = df['Pivot'] - (df['Prev_Day_High'] - df['Prev_Day_Low'])
        return df
