import pandas as pd
import numpy as np

class PerformanceMetrics:
    """Calculates KPIs like Sharpe Ratio, Max Drawdown, and Duration."""

    @staticmethod
    def calculate(df: pd.DataFrame, interval='1h') -> dict:
        strategy_ret = df['Strategy_Returns'].fillna(0)
        cum_ret = df['Cumulative_Returns'].iloc[-1]
        
        # Calculate time in market
        # For 1h, each row is 1 hour. For 15m, each row is 0.25 hours.
        freq_mult = 1.0 if interval == '1h' else 0.25
        time_in_market_hours = (df['Position'] != 0).sum() * freq_mult
        
        # Max Drawdown
        peak = (1 + df['Cumulative_Returns']).expanding().max()
        dd = ((1 + df['Cumulative_Returns']) - peak) / peak
        max_dd = dd.min()
        
        # Sharpe Ratio (Annualized)
        sharpe = (strategy_ret.mean() / strategy_ret.std()) * np.sqrt(8760 / freq_mult) if strategy_ret.std() != 0 else 0
        
        return {
            "Total Return": f"{cum_ret:.2%}",
            "Max Drawdown": f"{max_dd:.2%}",
            "Sharpe Ratio": f"{sharpe:.2f}",
            "Time in Market": f"{time_in_market_hours:.1f} hours",
            "Trades": int(np.abs(df['Signal']).sum())
        }
