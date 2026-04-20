import requests
import json
import logging
import time
from typing import Dict, Any, Optional

class FortressClient:
    """
    Upgraded Client for Fortress Security Platform (v3.0.0).
    Features: Heartbeat, Backoff Retries, and Secure Log Ingestion.
    """
    def __init__(self, base_url: str = "http://127.0.0.1:8000", api_key: str = None):
        self.base_url = base_url
        self.api_key = api_key
        self.logger = logging.getLogger("FortressClient")
        
        # Configure logging to match bot standard if not already set
        if not self.logger.handlers:
            handler = logging.FileHandler("bot_live_error.log")
            handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.INFO)

        self.token = None
        self.is_online = False
        self._last_auth_attempt = 0
        self._auth_interval = 300 # Try re-auth every 5 mins if offline
        
        self.heartbeat()

    def heartbeat(self) -> bool:
        """Checks if the Fortress Core is reachable."""
        try:
            res = requests.get(f"{self.base_url}/api/heartbeat", timeout=2)
            if res.status_code == 200:
                if not self.is_online:
                    self.logger.info("Fortress Security Core is ONLINE.")
                self.is_online = True
                return True
        except Exception:
            pass
        
        if self.is_online:
            self.logger.warning("Fortress Security Core went OFFLINE. Switching to local reporting.")
        self.is_online = False
        return False

    def _authenticate(self, retries=3):
        """Authenticates with the Fortress Core with exponential backoff."""
        if not self.is_online and not self.heartbeat():
            return False

        payload = {"username": "admin_mobile", "password": "secure_password"}
        for i in range(retries):
            try:
                res = requests.post(f"{self.base_url}/api/login", json=payload, timeout=2)
                if res.status_code == 200:
                    self.token = res.json().get("access_token")
                    self.logger.info("Successfully authenticated with Fortress Core.")
                    return True
            except Exception as e:
                wait = (2 ** i)
                self.logger.error(f"Auth failure (Attempt {i+1}/{retries}): {e}. Retrying in {wait}s...")
                time.sleep(wait)
        
        return False

    def _ensure_authenticated(self) -> bool:
        if self.token and self.is_online:
            return True
        
        now = time.time()
        if now - self._last_auth_attempt > 10: # Rate limit auth attempts
            self._last_auth_attempt = now
            return self._authenticate()
        return False

    def log_event(self, event_type: str, message: str, severity: str = "INFO"):
        """Sends a log event to Fortress for ingestion."""
        # Always log locally first
        log_msg = f"[{event_type}] {message}"
        if severity == "CRITICAL":
            self.logger.critical(log_msg)
        elif severity == "WARN":
            self.logger.warning(log_msg)
        else:
            self.logger.info(log_msg)

        if not self._ensure_authenticated():
            return

        # Attempt to report to Fortress
        payload = {
            "event_type": event_type,
            "message": message,
            "severity": severity
        }
        headers = {"Authorization": f"Bearer {self.token}"}
        
        try:
            res = requests.post(
                f"{self.base_url}/api/logs/ingest", 
                json=payload, 
                headers=headers,
                timeout=2
            )
            if res.status_code == 200:
                # Successfully reported
                pass
            else:
                self.logger.error(f"Failed to ingest log to Fortress: {res.text}")
        except Exception as e:
            self.logger.error(f"Uplink error during log ingest: {e}")
            self.is_online = False # Mark offline on network error

    def report_trade(self, action: str, symbol: str, price: float, amount: float):
        msg = f"TRADE EXECUTED: {action} {amount} {symbol} @ ${price}"
        self.log_event("TRADE_EXEC", msg, "INFO")

    def report_risk(self, metric: str, value: float, threshold: float):
        msg = f"RISK ALERT: {metric} is {value} (Limit: {threshold})"
        self.log_event("RISK_BREACH", msg, "CRITICAL")

    # --- SUPERVISION LOGIC ---
    def check_health(self, equity: float, hard_floor: float = 100.0):
        """Monitors account equity against a hard floor to prevent liquidation."""
        if equity < hard_floor:
            msg = f"SUPERVISION ALERT: Equity ${equity:.2f} is below hard floor ${hard_floor:.2f}!"
            self.log_event("HEALTH_CRITICAL", msg, "CRITICAL")
            return False
        return True

    def check_slippage(self, symbol: str, requested: float, executed: float, max_pct: float = 0.005):
        """Monitors for excessive slippage on order execution."""
        slippage = abs(executed - requested) / requested if requested > 0 else 0
        if slippage > max_pct:
            msg = f"SUPERVISION ALERT: High slippage on {symbol} - {slippage*100:.2f}% (Max: {max_pct*100:.2f}%)"
            self.log_event("SLIPPAGE_WARN", msg, "WARN")
            return False
        return True

    def check_stale_price(self, symbol: str, last_update: float, max_age: int = 60):
        """Monitors for stale price feeds from the exchange."""
        age = time.time() - last_update
        if age > max_age:
            msg = f"SUPERVISION ALERT: Stale price feed for {symbol} - {age:.0f}s old (Max: {max_age}s)"
            self.log_event("PRICE_STALE", msg, "CRITICAL")
            return False
        return True
