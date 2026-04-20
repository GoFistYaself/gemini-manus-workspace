import subprocess
import time
import os
import sys
from datetime import datetime

def run_resilient_bot(bot_args=None):
    """Starts the bot and restarts it automatically if it crashes."""
    project_dir = os.path.dirname(os.path.abspath(__file__))
    log_dir = os.path.join(project_dir, "logs")
    log_file = os.path.join(log_dir, "service_monitor.log")
    
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    print(f"--- BTC Quant Pro Service Monitor Started ---")
    print(f"Log: {log_file}")
    
    env = os.environ.copy()
    env["PYTHONPATH"] = project_dir

    restart_count = 0
    
    cmd = ["python", "run_bot.py"]
    if bot_args:
        cmd.extend(bot_args)
    
    # Check if we should use --live
    is_live = "--live" in cmd or (bot_args and any("live" in a.lower() for a in bot_args))

    while True:
        try:
            print(f"[{datetime.now()}] Starting Trading Bot (Attempt {restart_count + 1})...")
            
            # Start the process
            process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=project_dir,
                env=env,
                bufsize=1
            )
            
            # Send the confirmation if in live mode
            if is_live:
                process.stdin.write("LIVE\n")
                process.stdin.flush()
            
            # Monitor output in real-time
            with open(log_file, "a") as log:
                log.write(f"\n--- SESSION START: {datetime.now()} ---\n")
                log.flush()
                
                # We need to read from stdout without blocking the process
                # Reading line by line should be fine
                for line in process.stdout:
                    sys.stdout.write(line)
                    log.write(line)
                    log.flush()
            
            process.wait()
            
            if process.returncode != 0:
                print(f"\n[{datetime.now()}] Bot crashed with code {process.returncode}. Restarting in 10s...")
            else:
                print(f"\n[{datetime.now()}] Bot stopped normally. Restarting in 10s...")
                
            restart_count += 1
            time.sleep(10)
            
        except KeyboardInterrupt:
            print("\nStopping Service Monitor...")
            if 'process' in locals():
                process.terminate()
            break
        except Exception as e:
            print(f"Monitor Error: {e}")
            time.sleep(10)

if __name__ == "__main__":
    run_resilient_bot(sys.argv[1:])
