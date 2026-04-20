import time
import sys
import os
import logging
from src.bot.trading_bot import AITradingBot
from dotenv import load_dotenv
from src.core.execution import CoinbaseExecutionEngine

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("bot_live_automated.log"),
        logging.StreamHandler(sys.stdout)
    ]
)

def run_automated_live():
    # Load environment from @.env file
    # We are running from root, but the file is in btc_quant_pro
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "@.env")
    load_dotenv(dotenv_path=env_path)

    print("\n" + "!" * 50)
    print("CRITICAL: AUTOMATED LIVE TRADING MODE STARTING")
    print("REAL ORDERS WILL BE EXECUTED ON COINBASE")
    print("TARGET ROI: 1-3% DAILY | MONITORING: FORTRESS SENTINEL")
    print("!" * 50 + "\n")

    api_key = os.getenv('COINBASE_API_KEY')
    api_secret = os.getenv('COINBASE_API_SECRET')
    reserved_btc = float(os.getenv('RESERVED_BTC', '0.0'))
    
    if not api_key or not api_secret:
        print(f"Error: COINBASE_API_KEY or COINBASE_API_SECRET not found in {env_path}")
        return

    # Initialize Execution Engine (Live)
    execution_engine = CoinbaseExecutionEngine(reserved_btc=reserved_btc)
    
    print("--- BTC Quant Pro: AI Trading Bot (v2.0) ---")
    print("Initializing...")

    bot = AITradingBot(name="Fortress-Linked-Bot", execution_engine=execution_engine)
    bot.initialize()

    print("\n[SYSTEM] Connecting to Fortress Security Core...")
    print("[SYSTEM] Starting Live Tick Loop (Press Ctrl+C to stop)...")

    try:
        # Initial status report
        print(bot.get_status_report())
        
        # Main Loop
        while True:
            # In live mode, bot.live_tick() fetches real price from Coinbase engine
            bot.live_tick()
            time.sleep(30)
    except KeyboardInterrupt:
        print("\n[SYSTEM] Shutdown signal received.")
        print(bot.get_status_report())
        print("[SYSTEM] Bot stopped.")

if __name__ == "__main__":
    run_automated_live()
