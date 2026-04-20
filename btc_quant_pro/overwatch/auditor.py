import json
import logging
import os
from datetime import datetime
import pandas as pd

logger = logging.getLogger("Overwatch.Auditor")
logger.setLevel(logging.INFO)

class Auditor:
    def __init__(self, shadow_file, trade_file, max_drawdown=0.05, reserved_btc=0.0):
        self.shadow_file = shadow_file
        self.trade_file = trade_file
        self.max_drawdown = max_drawdown
        self.reserved_btc = reserved_btc
        self.alerts = []
        self.last_check_pos = 0

    def analyze_performance(self):
        """Calculates PnL, Win Rate, and Drawdown from trade logs."""
        try:
            if not os.path.exists(self.trade_file):
                return {"pnl": 0, "win_rate": 0, "drawdown": 0}
            
            with open(self.trade_file, 'r') as f:
                history = json.load(f)
            
            if not history:
                return {"pnl": 0, "win_rate": 0, "drawdown": 0}
                
            pnl_series = []
            running_pnl = 0
            wins = 0
            losses = 0
            
            for event in history:
                if event['action'] == 'CLOSE':
                    pnl = float(event.get('pnl', 0.0))
                    fee = float(event.get('fee', 0.0))
                    net = pnl - fee
                    running_pnl += net
                    pnl_series.append(running_pnl)
                    if net > 0: wins += 1
                    else: losses += 1
            
            # Drawdown Calculation (Peak to Trough)
            max_pnl = 0
            current_drawdown = 0
            if pnl_series:
                peak = max(pnl_series)
                # If current running pnl is less than peak, calculate drawdown relative to peak
                # Simplified: Assume base capital is large enough, or track equity if available
                # Here we track raw PnL drawdown from peak
                current_drawdown = peak - running_pnl if running_pnl < peak else 0
            
            total_trades = wins + losses
            win_rate = (wins / total_trades * 100) if total_trades > 0 else 0
            
            return {
                "net_pnl": running_pnl,
                "win_rate": win_rate,
                "drawdown_amt": current_drawdown,
                "trades": total_trades
            }
        except Exception as e:
            logger.error(f"Performance Analysis Failed: {e}")
            return {}

    def validate_strategy(self):
        """Checks shadow logs for strategy violations (e.g., Signal vs Trade direction)."""
        violations = []
        try:
            if not os.path.exists(self.shadow_file):
                return violations

            with open(self.shadow_file, 'r') as f:
                # Only read new lines since last check (optimization)
                f.seek(self.last_check_pos)
                lines = f.readlines()
                self.last_check_pos = f.tell()

            for line in lines:
                try:
                    event = json.loads(line)
                    if event['type'] == 'TRADE_OPEN':
                        payload = event['payload']
                        size = float(payload.get('size', 0))
                        score = float(payload.get('score', 0))
                        
                        # Rule 1: Buy (size > 0) requires Score > 0.5 (or strategy threshold)
                        # Rule 2: Sell (size < 0) requires Score < -0.5
                        # We use 0.5 as a safety margin, though bot uses higher thresholds
                        if size > 0 and score < 0.5:
                            msg = f"Strategy Violation: BUY executed with weak score ({score:.2f})"
                            violations.append(msg)
                            logger.warning(msg)
                        elif size < 0 and score > -0.5:
                            msg = f"Strategy Violation: SELL executed with weak score ({score:.2f})"
                            violations.append(msg)
                            logger.warning(msg)
                            
                except json.JSONDecodeError:
                    continue
                    
            return violations
        except Exception as e:
            logger.error(f"Strategy Validation Failed: {e}")
            return []

    def check_compliance(self, current_btc_balance):
        """Ensures reserved BTC is not touched."""
        if current_btc_balance < self.reserved_btc:
            msg = f"COMPLIANCE ALERT: Reserved BTC Breach! (Current: {current_btc_balance} < Reserved: {self.reserved_btc})"
            logger.critical(msg)
            return [msg]
        return []

    def get_risk_status(self):
        perf = self.analyze_performance()
        drawdown = perf.get('drawdown_amt', 0)
        
        # Risk Check
        risk_level = "LOW"
        if drawdown > 500: # Arbitrary $500 threshold for warning
            risk_level = "MEDIUM"
        if drawdown > 1000:
            risk_level = "HIGH"
            
        return {
            "risk_level": risk_level,
            "metrics": perf
        }
