import time
import sys
import os
import logging
import argparse

# Ensure the root directory is in sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.bot.trading_bot import AITradingBot
from dotenv import load_dotenv
from src.core.execution import CoinbaseExecutionEngine, PaperWallet

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("bot_live_automated.log")
    ]
)

def run_live_bot():
    parser = argparse.ArgumentParser(description='BTC Quant Pro Trading Bot')
    parser.add_argument('--live', action='store_true', help='Enable Live Trading Mode (Real Money)')
    parser.add_argument('--mode', type=str, choices=['paper', 'live'], help='Trading mode')
    parser.add_argument('--config', type=str, help='Path to config file')
    parser.add_argument('--log-level', type=str, default='INFO', help='Logging level')
    parser.add_argument('--force', action='store_true', help='Skip confirmation prompt for live trading')
    args = parser.parse_args()

    # Set log level based on argument
    numeric_level = getattr(logging, args.log_level.upper(), None)
    if isinstance(numeric_level, int):
        logging.getLogger().setLevel(numeric_level)

    # Load environment from @.env file
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '@.env')
    load_dotenv(dotenv_path=env_path)

    # Mode Selection
    execution_engine = None
    is_live_mode = args.live or args.mode == 'live'
    
    if is_live_mode:
        
        print("\n" + "!" * 50)
        print("WARNING: LIVE TRADING MODE ENABLED")
        print("REAL ORDERS WILL BE EXECUTED ON COINBASE")
        print("!" * 50 + "\n")

        if not args.force:
            confirm = input("Type 'LIVE' to confirm real money trading: ")
            if confirm != "LIVE":
                print("Aborting live mode.")
                return
        else:
            print("[INFO] --force flag detected. Skipping manual confirmation.")

        api_key = os.getenv('COINBASE_API_KEY')
        api_secret = os.getenv('COINBASE_API_SECRET')
        reserved_btc = float(os.getenv('RESERVED_BTC', '0.0'))
        if not api_key or not api_secret:
            print("Error: COINBASE_API_KEY or COINBASE_API_SECRET not found in environment.")
            print("Please add them to your @.env file.")
            return

        execution_engine = CoinbaseExecutionEngine(reserved_btc=reserved_btc)
    else:
        print("[INFO] Running in Paper Trading Mode (Simulation)")

    print("--- BTC Quant Pro: AI Trading Bot (v2.0) ---")
    print("Initializing...")

    # --- FLEET MANAGER: Multi-Coin Strategy ---
    import ccxt
    api_key = os.getenv('COINBASE_API_KEY')
    api_secret = os.getenv('COINBASE_API_SECRET')
    reserved_btc = float(os.getenv('RESERVED_BTC', '0.0'))
    print("[FLEET] Scanning Coinbase for existing bags to take over...")
    
    # Temporarily bypass CCXT execution engine just to read balances for initialization
    exchange = ccxt.coinbase({
        'apiKey': api_key,
        'secret': api_secret.replace('\\n', '\n') if api_secret else ''
    })
    
    fleet = []
    try:
        bal = exchange.fetch_balance()
        totals = bal.get('total', {})
        
        # Base targets to always trade
        target_symbols = ['BTC-USD', 'SOL-USD']
        
        # Find all coins with a balance > 0 to take over
        delisted_symbols = ['ERN-USD', 'RLY-USD', 'CLV-USD', 'BOND-USD']
        for asset, amount in totals.items():
            if amount > 0 and asset not in ['USD', 'USDC', 'EUR', 'GBP']:
                symbol = f"{asset}-USD"
                if symbol not in target_symbols and symbol not in delisted_symbols:
                    target_symbols.append(symbol)
                    
        print(f"[FLEET] Mobilizing {len(target_symbols)} autonomous agents for: {', '.join(target_symbols)}")
        
        for sym in target_symbols:
            if args.live or args.mode == 'live':
                engine = CoinbaseExecutionEngine(symbol=sym, reserved_btc=reserved_btc)
            else:
                engine = PaperWallet(balance=500.0)
            bot = AITradingBot(name=f"Quant-{sym}", symbol=sym, execution_engine=engine)
            bot.initialize()
            fleet.append(bot)
            
    except Exception as e:
        print(f"[FLEET ERROR] Could not initialize fleet: {e}")
        return

    print("\n[SYSTEM] Connecting to Fortress Security Core...")
    sys.stdout.flush()
    print("[SYSTEM] Starting Fleet Live Tick Loop (Press Ctrl+C to stop)...")
    sys.stdout.flush()

    try:
        while True:
            for bot in fleet:
                try:
                    bot.live_tick()
                except Exception as e:
                    pass # Ignore 429 rate limits or minor tick errors silently
                import time
                time.sleep(1) # Stagger API requests
            sys.stdout.flush()
            time.sleep(3)
    except KeyboardInterrupt:
        print("\n[SYSTEM] Shutdown signal received.")
        for bot in fleet:
            print(bot.get_status_report())
        print("[SYSTEM] Fleet stopped.")

if __name__ == "__main__":
    run_live_bot()
