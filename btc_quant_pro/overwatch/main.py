import time
import json
import logging
import os
import sys
from datetime import datetime

# Add current directory to path for imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from guardian import Guardian
from auditor import Auditor

# Configure logging
# Let's put logs inside btc_quant_pro/logs for consistency
LOG_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "logs"))
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)
    
logging.basicConfig(
    filename=os.path.join(LOG_DIR, "overwatch_supervisor.log"),
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
console = logging.StreamHandler()
console.setLevel(logging.INFO)
logging.getLogger('').addHandler(console)

logger = logging.getLogger("Overwatch.Main")

# Paths relative to root (C:\Users\1mpal)
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
# Correct paths for internal data
SHADOW_FILE = os.path.join(ROOT_DIR, "btc_quant_pro", "shadow_data", "Fortress-Linked-Bot_history.jsonl")
TRADE_FILE = os.path.join(ROOT_DIR, "btc_quant_pro", "logs", "coinbase_trade_history.json")
STATUS_FILE = os.path.join(ROOT_DIR, "btc_quant_pro", "logs", "supervisor_status.json")

def main():
    print("="*60)
    print("OVERWATCH: SENTINEL SUPERVISOR FOR BTC QUANT PRO")
    print("Monitoring Process, Strategy, Risk, and Compliance")
    print("="*60)

    # Guardian runs from btc_quant_pro root so it can find 'src' modules
    bot_root = os.path.join(ROOT_DIR, "btc_quant_pro")
    guardian = Guardian(target_script="run_live_automated.py", root_dir=bot_root)
    auditor = Auditor(shadow_file=SHADOW_FILE, trade_file=TRADE_FILE, reserved_btc=0.0)

    # Initial check
    if not guardian.check_health():
        logger.warning("Bot not running. Attempting initial launch...")
        if not guardian.start_bot():
            logger.error("Failed to start bot. Exiting.")
            return

    try:
        while True:
            # 1. Process Health Check
            alive = guardian.check_health()
            if not alive:
                logger.critical("Bot Process Died! Initiating Recovery...")
                if guardian.recover():
                    logger.info("Recovery Successful.")
                else:
                    logger.error("Recovery Failed. Retrying in next loop.")
            
            # 2. Risk & Strategy Audit
            risk_status = auditor.get_risk_status()
            strategy_violations = auditor.validate_strategy()
            
            # 3. Reporting
            status_report = {
                "timestamp": datetime.now().isoformat(),
                "process": guardian.get_status(),
                "risk": risk_status,
                "alerts": strategy_violations,
                "version": "Overwatch v1.0"
            }
            
            # Write status to file for Dashboard integration
            try:
                with open(STATUS_FILE, 'w') as f:
                    json.dump(status_report, f, indent=4)
            except Exception as e:
                logger.error(f"Failed to write status file: {e}")
            
            # Console Summary
            pnl = risk_status['metrics'].get('net_pnl', 0)
            status_line = f"[OVERWATCH] Status: {status_report['process']['status']} | Risk: {risk_status['risk_level']} | PnL: ${pnl:.2f}"
            print(status_line)
            
            time.sleep(10) # Check every 10 seconds

    except KeyboardInterrupt:
        print("\nOverwatch Shutting Down.")

if __name__ == "__main__":
    main()
