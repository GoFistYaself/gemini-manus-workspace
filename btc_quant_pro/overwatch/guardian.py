import os
import sys
import time
import subprocess
import psutil
import logging
from datetime import datetime

# Setup logging specific to Overwatch
logger = logging.getLogger("Overwatch.Guardian")
logger.setLevel(logging.INFO)

class Guardian:
    def __init__(self, target_script="run_live_automated.py", root_dir="."):
        self.target_script = target_script
        self.root_dir = os.path.abspath(root_dir)
        self.process = None
        self.start_time = None
        self.restart_count = 0
        self.max_restarts = 5
        self.last_restart = datetime.min

    def find_existing_process(self):
        """Scans for an existing instance of the bot."""
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                if proc.info['cmdline'] and self.target_script in ' '.join(proc.info['cmdline']):
                    return proc
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
        return None

    def start_bot(self):
        """Launches the bot process."""
        if self.find_existing_process():
            logger.info("Bot is already running.")
            return

        # Explicitly use sys.executable (python.exe) and the target script
        cmd = [sys.executable, self.target_script]
        logger.info(f"Starting bot: {' '.join(cmd)}")
        
        try:
            # Run in new console window so it persists independent of supervisor
            creation_flags = subprocess.CREATE_NEW_CONSOLE if os.name == 'nt' else 0
            
            # Use absolute path for target_script to avoid ambiguity
            script_path = os.path.join(self.root_dir, self.target_script)
            cmd = [sys.executable, script_path]

            self.process = subprocess.Popen(
                cmd, 
                cwd=self.root_dir,
                creationflags=creation_flags
            )
            self.start_time = datetime.now()
            logger.info(f"Bot started with PID: {self.process.pid}")
            return True
        except Exception as e:
            logger.error(f"Failed to start bot: {e}")
            return False

    def check_health(self):
        """Checks if the bot process is alive."""
        # First, check our internal reference
        if self.process:
            if self.process.poll() is None:
                return True
            else:
                logger.warning(f"Bot process {self.process.pid} died with code {self.process.returncode}.")
                self.process = None
        
        # Fallback: Check if ANY instance is running (maybe started manually)
        proc = self.find_existing_process()
        if proc:
            if not self.process:
                 logger.info(f"Found external bot process: {proc.pid}")
            self.process = proc
            return True
            
        return False

    def recover(self):
        """Attempt to restart the bot if it fails."""
        now = datetime.now()
        if (now - self.last_restart).total_seconds() < 60:
            logger.warning("Restart throttling active (waiting 60s)...")
            return False

        if self.restart_count >= self.max_restarts:
            logger.critical("Max restarts exceeded. Manual intervention required.")
            return False

        logger.warning(f"Initiating Recovery Protocol... (Attempt {self.restart_count + 1}/{self.max_restarts})")
        
        if self.start_bot():
            self.restart_count += 1
            self.last_restart = now
            return True
        return False

    def get_status(self):
        alive = self.check_health()
        uptime = "N/A"
        if alive and self.start_time:
            uptime = str(datetime.now() - self.start_time).split('.')[0]
        elif alive and self.process:
            try:
                create_time = datetime.fromtimestamp(self.process.create_time())
                uptime = str(datetime.now() - create_time).split('.')[0]
            except: pass
            
        return {
            "status": "ONLINE" if alive else "OFFLINE",
            "pid": self.process.pid if self.process else None,
            "uptime": uptime,
            "restarts": self.restart_count
        }
