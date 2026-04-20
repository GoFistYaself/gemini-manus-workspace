import pandas as pd
import numpy as np

class Backtester:
    """Simulates trading based on signals, dynamic SL/TP, and fees."""
    
    def __init__(self, risk_multiple=1.5, reward_multiple=3.0, sl_offset_pct=0.0, fee_pct=0.001):
        self.risk_multiple = risk_multiple
        self.reward_multiple = reward_multiple
        self.sl_offset_pct = sl_offset_pct
        self.fee_pct = fee_pct # Default 0.1% per trade

    def run(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df['Strategy_Returns'] = 0.0
        df['Position'] = 0
        
        active_trade = None
        
        for i in range(len(df)):
            current_idx = df.index[i]
            row = df.iloc[i]
            
            if active_trade:
                # Manage Open Position
                entry_price, sl, tp, pos_type = active_trade
                closed = False
                ret = 0.0
                
                if pos_type == 1: # Long
                    if row['Low'] <= sl:
                        ret = (sl - entry_price) / entry_price
                        closed = True
                    elif not np.isnan(tp) and row['High'] >= tp:
                        ret = (tp - entry_price) / entry_price
                        closed = True
                else: # Short
                    if row['High'] >= sl:
                        ret = (entry_price - sl) / entry_price
                        closed = True
                    elif not np.isnan(tp) and row['Low'] <= tp:
                        ret = (entry_price - tp) / entry_price
                        closed = True
                
                if closed:
                    # Subtract exit fee
                    df.at[current_idx, 'Strategy_Returns'] = ret - self.fee_pct
                    active_trade = None
                else:
                    prev_close = df['Close'].iloc[i-1]
                    step_ret = (row['Close'] - prev_close) / prev_close if pos_type == 1 else (prev_close - row['Close']) / prev_close
                    df.at[current_idx, 'Strategy_Returns'] = step_ret
                    df.at[current_idx, 'Position'] = pos_type
            
            else:
                # Open New Position
                signal = row['Signal']
                if signal != 0 and not np.isnan(row['ATR']):
                    entry = row['Close']
                    sl_dist = (self.risk_multiple * row['ATR']) + (self.sl_offset_pct * entry)
                    sl = entry - (signal * sl_dist)
                    tp = entry + (signal * self.reward_multiple * row['ATR'])
                    active_trade = (entry, sl, tp, signal)
                    
                    # Subtract entry fee
                    df.at[current_idx, 'Strategy_Returns'] = -self.fee_pct
                    df.at[current_idx, 'Position'] = signal

        df['Cumulative_Returns'] = (1 + df['Strategy_Returns']).cumprod() - 1
        return df
