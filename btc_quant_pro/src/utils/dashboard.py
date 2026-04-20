import json
import os
import sys
from datetime import datetime

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def format_currency(val):
    if val == "-": return "-"
    return f"${val:,.2f}"

def show_dashboard(mode="live"):
    history_file = "logs/coinbase_trade_history.json" if mode == "live" else "logs/paper_trade_history.json"
    
    if not os.path.exists(history_file):
        # Only clear screen if we are going to show something new or error
        # clear_screen()
        print(f"Waiting for trade history at {history_file}...")
        return

    try:
        with open(history_file, 'r') as f:
            history = json.load(f)
    except Exception as e:
        print(f"Error reading history: {e}")
        return

    clear_screen()
    title_mode = "LIVE (COINBASE)" if mode == "live" else "PAPER (SIMULATION)"
    print("="*75)
    print(f"      BTC QUANT PRO: {title_mode} DASHBOARD")
    print("="*75)

    if not history:
        print("No trade history recorded yet.")
        return

    # Calculate Stats
    total_pnl = 0.0
    total_fees = 0.0
    wins = 0
    losses = 0
    
    table_rows = []
    
    for event in history:
        # Handle mixed formats from Paper/Live
        ts_str = event.get('timestamp', '')
        if ts_str:
            try:
                ts = datetime.fromisoformat(ts_str).strftime('%Y-%m-%d %H:%M')
            except:
                ts = ts_str[:16]
        else:
            ts = "N/A"
            
        fee = float(event.get('fee', 0.0))
        total_fees += fee
        
        if event['action'] == 'OPEN':
            amount = float(event.get('amount', 0.0))
            price = float(event.get('price', 0.0))
            direction = event.get('direction', 'UNK')
            row = [ts, "OPEN", direction, f"{amount:.4f}", format_currency(price), "-"]
            table_rows.append(row)
        else:
            pnl = float(event.get('pnl', 0.0))
            price = float(event.get('price', event.get('exit_price', 0.0)))
            reason = event.get('reason', event.get('exit_reason', 'Signal'))[:8]
            
            total_pnl += pnl
            if pnl > 0: wins += 1
            elif pnl < 0: losses += 1
            
            row = [ts, "CLOSE", reason, "-", format_currency(price), format_currency(pnl)]
            table_rows.append(row)

    # Display Table (Simple Column formatting)
    header = f"{'Timestamp':<18} | {'Type':<6} | {'Info':<10} | {'Size':<8} | {'Price':<12} | {'PnL':<10}"
    print(header)
    print("-" * len(header))
    
    for r in table_rows[-15:]: # Show last 15 entries
        print(f"{r[0]:<18} | {r[1]:<6} | {r[2]:<10} | {r[3]:<8} | {r[4]:<12} | {r[5]:<10}")

    print("-" * len(header))
    
    # Summary Section
    total_trades = wins + losses
    win_rate = (wins / total_trades * 100) if total_trades > 0 else 0
    
    print("\nSUMMARY STATS:")
    print(f"  Total Trades: {total_trades}")
    print(f"  Win Rate:     {win_rate:.1f}% ({wins}W / {losses}L)")
    print(f"  Gross PnL:    {format_currency(total_pnl)}")
    print(f"  Total Fees:   {format_currency(total_fees)}")
    print(f"  Net PnL:      {format_currency(total_pnl - total_fees)}")
    print("="*75)
    print("\n[Auto-refreshing in 30s...] Press Ctrl+C to exit.")

if __name__ == "__main__":
    import time
    import argparse
    
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", type=str, default="live", choices=["live", "paper"], help="Dashboard mode")
    args = parser.parse_args()
    
    try:
        while True:
            show_dashboard(args.mode)
            time.sleep(30)
    except KeyboardInterrupt:
        print("\nDashboard closed.")
