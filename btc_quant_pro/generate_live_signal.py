import yfinance as yf
import pandas as pd
import sys
import os
from datetime import datetime

# Adjust path to find modules
sys.path.append(os.getcwd())
# sys.path.append(os.path.join(os.getcwd(), 'btc_quant_pro'))
from btc_quant_pro.src.core.indicators import IndicatorCalculator
from btc_quant_pro.src.core.signal_engine import SignalEngine
from btc_quant_pro.src.core.pattern_engine import PatternEngine

def get_live_signal():
    print("\n[SYSTEM] Connecting to Market Data Feed (BTC-USD)...")
    
    # 1. Fetch Data (Last 60 days to ensure enough for EMA-200)
    try:
        # Fetching more data to ensure indicators settle
        ticker = yf.Ticker("BTC-USD")
        df = ticker.history(period="60d", interval="1h")
        
        if df.empty:
            print("[ERROR] No data received from Exchange.")
            return
            
        print(f"[SYSTEM] Data Acquired: {len(df)} candles.")
        
        # 2. Process Indicators
        print("[SYSTEM] Calculating Technical Indicators...")
        df = IndicatorCalculator.apply_indicators(df)
        
        # 3. Initialize Engines
        print("[SYSTEM] initializing AI Engines (Pattern & Signal)...")
        pe = PatternEngine()
        # Train pattern engine briefly on recent history to calibrate
        pe.learn_performance(df.iloc[:-1]) 
        
        se = SignalEngine(interval='1h', pattern_engine=pe)
        
        # 4. Generate Signals
        print("[SYSTEM] Generating Alpha...")
        df_sig = se.generate_signals(df)
        
        # 5. Analyze Latest Candle
        latest = df_sig.iloc[-1]
        prev = df_sig.iloc[-2]
        
        current_price = latest['Close']
        p_score = latest.get('P_Score', 0)
        ema_20 = latest['EMA_20']
        ema_50 = latest['EMA_50']
        ema_200 = latest['EMA_200']
        rsi = latest['rsi_value']
        regime = latest.get('Regime', 'NEUTRAL')
        vol = latest['Volume']
        vol_sma = latest['Volume_SMA']
        
        print("\n" + "="*40)
        print(f"   BTC QUANT PRO | LIVE SIGNAL REPORT")
        print("="*40)
        print(f"Time:       {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Price:      ${current_price:,.2f}")
        print(f"Trend:      {'BULLISH' if ema_50 > ema_200 else 'BEARISH'} (EMA50 vs EMA200)")
        print(f"Regime:     {regime}")
        print(f"RSI (14):   {rsi:.2f}")
        print(f"Volume:     {vol:.2f} (SMA: {vol_sma:.2f})")
        print(f"AI Score:   {p_score:.2f} (Pattern Confidence)")
        print("-" * 40)
        
        # Decision Logic (Simplified for output)
        recommendation = "HOLD / WAIT"
        reason = "Market is ranging or conflicting signals."
        
        # Check Signal Column
        if latest['Signal'] == 1:
            recommendation = "BUY / LONG"
            reason = "AI Signal Engine Triggered (Trend + Pattern)"
        elif latest['Signal'] == -1:
            recommendation = "SELL / SHORT"
            reason = "AI Signal Engine Triggered (Bearish Structure)"
        else:
            # Fallback advice if no hard signal this exact hour
            if p_score > 1.5 and rsi < 70:
                recommendation = "ACCUMULATE (Weak Buy)"
                reason = "High Pattern Confidence (Bullish) despite no hard trigger."
            elif p_score < -1.5 and rsi > 30:
                recommendation = "REDUCE EXPOSURE (Weak Sell)"
                reason = "High Pattern Confidence (Bearish)."
        
        print(f"ACTION:     >> {recommendation} <<")
        print(f"Reason:     {reason}")
        print("="*40 + "\n")
        
    except Exception as e:
        print(f"[CRITICAL ERROR] {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    get_live_signal()
