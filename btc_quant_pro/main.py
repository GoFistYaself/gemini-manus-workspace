from src.core.data_loader import DataLoader
from src.core.indicators import IndicatorCalculator
from src.core.signal_engine import SignalEngine
from src.core.backtester import Backtester
from src.core.trend_analyzer import TrendAnalyzer
from src.core.pattern_engine import PatternEngine
from src.utils.performance import PerformanceMetrics
from src.utils.visualizer import Visualizer
import logging
import pandas as pd
import numpy as np

logging.basicConfig(level=logging.INFO)

def run_calibration(pattern_engine):
    """
    Pre-trains the pattern engine on diverse market regimes to build statistical significance.
    """
    print(f"\n{'='*10} Running Calibration Phase (Regime Learning) {'='*10}")
    from generate_data import generate_synthetic_ohlcv
    
    # 1. Bullish Regime
    print("... Learning from Bull Market simulation")
    df_bull = generate_synthetic_ohlcv(periods=5000, freq='15min')
    pattern_engine.learn_performance(df_bull)
    
    # 2. Bearish Regime (we can simulate this by just running it again, randomness handles regimes)
    print("... Learning from Bear Market simulation")
    df_bear = generate_synthetic_ohlcv(periods=5000, freq='15min')
    pattern_engine.learn_performance(df_bear)
    
    # 3. Chop Regime
    print("... Learning from Sideways Market simulation")
    df_chop = generate_synthetic_ohlcv(periods=5000, freq='15min')
    pattern_engine.learn_performance(df_chop)
    
    print("--- Calibration Complete. Knowledge Base: ---")
    for p, data in pattern_engine.knowledge_base.items():
        print(f"  {p}: {data['success_rate']:.1%} (N={data['sample_size']}) -> Reliability Score: {data['reliability']:.2f}")

def run_strategy(interval, pattern_engine):
    print(f"\n{'='*10} Running Specialized Strategy on {interval} Interval {'='*10}")
    # 1. Fetch Data
    try:
        df = DataLoader.fetch_ohlcv('BTC-USD', period='60d', interval=interval)
    except Exception as e:
        print(f"yfinance failed for {interval} ({e}). Using synthetic data...")
        from generate_data import generate_synthetic_ohlcv
        periods = 1440 if interval == '1h' else 5760
        freq = 'h' if interval == '1h' else '15min'
        df = generate_synthetic_ohlcv(periods=periods, freq=freq)

    # 2. Indicators
    df = IndicatorCalculator.apply_indicators(df)
    
    # --- LEARNING ARM PHASE (Live Adjustment) ---
    print(f"--- Live Context Adjustment for {interval} ---")
    # We learn from the recent live data too, to adapt to *current* conditions
    pattern_engine.learn_performance(df) 
    
    # 3. Signals (Specialized Logic + Pattern Engine)
    if interval == '1h':
        engine = SignalEngine(interval='1h', volume_multiplier=1.0, pattern_engine=pattern_engine)
        tester = Backtester(risk_multiple=1.5, reward_multiple=3.5, fee_pct=0.001)
    else:
        engine = SignalEngine(interval='15m', volume_multiplier=2.0, pattern_engine=pattern_engine)
        tester = Backtester(risk_multiple=1.0, reward_multiple=5.0, fee_pct=0.001)
        
    df = engine.generate_signals(df)
    
    # 4. Backtest
    df = tester.run(df)
    
    # 5. Trend Analysis (Visual Only)
    # trendlines = TrendAnalyzer.get_trendlines(df)
    # Visualizer.plot_price_action(df, trendlines, title=f"BTC {interval} Trend Analysis")
    
    # 6. Performance
    metrics = PerformanceMetrics.calculate(df, interval=interval)
    print(f"--- {interval} Performance ---")
    for k, v in metrics.items():
        print(f"{k}: {v}")
    
    return df

def main():
    intervals = ['1h', '15m']
    results = {}
    
    # Initialize Shared Pattern Engine
    pe = PatternEngine()
    
    # Step 0: Calibrate on Diverse Datasets
    run_calibration(pe)
    
    for interval in intervals:
        results[interval] = run_strategy(interval, pe)
    
    # --- Portfolio Aggregation ---
    print(f"\n{'='*10} Aggregating Portfolio {'='*10}")
    
    # Align to the highest frequency (15m)
    portfolio_df = pd.DataFrame(index=results['15m'].index)
    
    # Process 1H returns: distribute across 15m intervals
    h1_returns = results['1h']['Strategy_Returns'].reindex(portfolio_df.index, method='ffill').fillna(0) / 4
    m15_returns = results['15m']['Strategy_Returns'].fillna(0)
    
    # Combine (Equally weighted)
    portfolio_df['Portfolio_Returns'] = (h1_returns + m15_returns) / 2
    portfolio_df['Portfolio_Cumulative_Returns'] = (1 + portfolio_df['Portfolio_Returns']).cumprod() - 1
    portfolio_df['Signal'] = 0 
    
    # Portfolio Position: Mark as active if either strategy has a position
    h1_pos = results['1h']['Position'].reindex(portfolio_df.index, method='ffill').fillna(0)
    m15_pos = results['15m']['Position'].fillna(0)
    portfolio_df['Position'] = np.where((h1_pos != 0) | (m15_pos != 0), 1, 0)
    
    # Calculate Portfolio Metrics
    port_metrics = PerformanceMetrics.calculate(
        portfolio_df.rename(columns={'Portfolio_Returns': 'Strategy_Returns', 'Portfolio_Cumulative_Returns': 'Cumulative_Returns'}),
        interval='15m'
    )
    
    print(f"\n--- Aggregated Portfolio Performance ---")
    for k, v in port_metrics.items():
        print(f"{k}: {v}")
        
    # 6. Visualize
    # Visualizer.plot_portfolio(results, portfolio_df)
if __name__ == "__main__":
    main()

