import json
import os
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from datetime import datetime
import pandas as pd

app = FastAPI(title="BTC Quant Pro Dashboard")

LOG_FILE = "bot_live_automated.log"
TRADE_HISTORY = "btc_quant_pro/logs/coinbase_trade_history.json"
SHADOW_DATA = "btc_quant_pro/shadow_data/Fortress-Linked-Bot_history.jsonl"
SUPERVISOR_STATUS = "btc_quant_pro/logs/supervisor_status.json"

def get_supervisor_status():
    if not os.path.exists(SUPERVISOR_STATUS):
        return {"process": {"status": "UNKNOWN"}, "risk": {"risk_level": "N/A"}}
    try:
        with open(SUPERVISOR_STATUS, 'r') as f:
            return json.load(f)
    except:
        return {"process": {"status": "ERROR"}, "risk": {"risk_level": "ERROR"}}

def get_latest_log_entries(n=20):
    if not os.path.exists(LOG_FILE):
        return ["Log file not found."]
    try:
        with open(LOG_FILE, 'r') as f:
            lines = f.readlines()
            return [line.strip() for line in lines[-n:]]
    except:
        return ["Error reading log."]

def get_trade_stats():
    if not os.path.exists(TRADE_HISTORY):
        return {"total_trades": 0, "win_rate": 0, "net_pnl": 0, "history": []}
    
    try:
        with open(TRADE_HISTORY, 'r') as f:
            history = json.load(f)
            
        wins = 0
        losses = 0
        net_pnl = 0.0
        
        for event in history:
            if event['action'] == 'CLOSE':
                pnl = float(event.get('pnl', 0.0))
                fee = float(event.get('fee', 0.0))
                net_pnl += (pnl - fee)
                if pnl > 0: wins += 1
                else: losses += 1
                
        total_trades = wins + losses
        win_rate = (wins / total_trades * 100) if total_trades > 0 else 0
        
        return {
            "total_trades": total_trades,
            "win_rate": f"{win_rate:.1f}%",
            "net_pnl": f"${net_pnl:,.2f}",
            "net_pnl_val": net_pnl,
            "history": history[-10:] # Last 10
        }
    except:
        return {"error": "Error parsing trade history", "net_pnl": "$0.00", "net_pnl_val": 0.0}

@app.get("/", response_class=HTMLResponse)
async def index():
    log_entries = get_latest_log_entries()
    stats = get_trade_stats()
    supervisor = get_supervisor_status()
    
    proc_status = supervisor.get('process', {}).get('status', 'UNKNOWN')
    risk_level = supervisor.get('risk', {}).get('risk_level', 'N/A')
    uptime = supervisor.get('process', {}).get('uptime', 'N/A')
    
    net_pnl_str = stats.get('net_pnl', '$0.00')
    net_pnl_val = stats.get('net_pnl_val', 0.0)
    pnl_color = 'green' if net_pnl_val >= 0 else 'red'
    
    html_content = f"""
    <html>
        <head>
            <title>BTC Quant Pro Live</title>
            <meta http-equiv="refresh" content="30">
            <style>
                body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #121212; color: #e0e0e0; margin: 20px; }}
                .container {{ max-width: 1200px; margin: auto; }}
                .header {{ display: flex; justify-content: space-between; align-items: center; border-bottom: 2px solid #333; padding-bottom: 10px; }}
                .status-online {{ color: #4caf50; font-weight: bold; }}
                .status-offline {{ color: #f44336; font-weight: bold; }}
                .risk-low {{ color: #4caf50; }}
                .risk-med {{ color: #ff9800; }}
                .risk-high {{ color: #f44336; }}
                .card-container {{ display: flex; gap: 20px; margin-top: 20px; }}
                .card {{ background: #1e1e1e; padding: 20px; border-radius: 8px; flex: 1; border: 1px solid #333; }}
                .card h2 {{ margin-top: 0; color: #bb86fc; font-size: 1.2rem; }}
                .stat-val {{ font-size: 2rem; font-weight: bold; margin: 10px 0; }}
                .log-box {{ background: #000; padding: 15px; border-radius: 5px; font-family: 'Courier New', Courier, monospace; font-size: 0.9rem; height: 300px; overflow-y: auto; border: 1px solid #444; }}
                table {{ width: 100%; border-collapse: collapse; margin-top: 10px; }}
                th, td {{ text-align: left; padding: 8px; border-bottom: 1px solid #333; font-size: 0.9rem; }}
                th {{ color: #888; }}
                .green {{ color: #4caf50; }}
                .red {{ color: #f44336; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>BTC Quant Pro <span style="font-size: 1rem; color: #888;">v2.0 Live</span></h1>
                    <div>
                        Supervisor: <span class="{'status-online' if proc_status == 'ONLINE' else 'status-offline'}">{proc_status}</span> 
                        | Uptime: {uptime}
                        | Risk: <span class="{'risk-low' if risk_level == 'LOW' else 'risk-med' if risk_level == 'MEDIUM' else 'risk-high'}">{risk_level}</span>
                    </div>
                </div>
                
                <div class="card-container">
                    <div class="card">
                        <h2>Net PnL</h2>
                        <div class="stat-val {pnl_color}">{net_pnl_str}</div>
                    </div>
                    <div class="card">
                        <h2>Win Rate</h2>
                        <div class="stat-val">{stats.get('win_rate', '0%')}</div>
                    </div>
                    <div class="card">
                        <h2>Total Trades</h2>
                        <div class="stat-val">{stats.get('total_trades', 0)}</div>
                    </div>
                </div>

                <div style="display: flex; gap: 20px; margin-top: 20px;">
                    <div class="card" style="flex: 2;">
                        <h2>Recent Trade History</h2>
                        <table>
                            <thead>
                                <tr>
                                    <th>Time</th>
                                    <th>Action</th>
                                    <th>Price</th>
                                    <th>PnL</th>
                                </tr>
                            </thead>
                            <tbody>
                                {"".join([f"<tr><td>{t.get('timestamp','')[11:16]}</td><td>{t.get('action')}</td><td>${float(t.get('price',0)):,.2f}</td><td class='{'green' if float(t.get('pnl',0)) > 0 else 'red'}'>{f'${float(t.get('pnl',0)):,.2f}' if t.get('action') == 'CLOSE' else '-'}</td></tr>" for t in stats.get('history', [])[::-1]])}
                            </tbody>
                        </table>
                        { '<p style="text-align:center; color:#666;">No trades recorded yet in this session.</p>' if not stats.get('history') else '' }
                    </div>
                    <div class="card" style="flex: 3;">
                        <h2>Live System Logs</h2>
                        <div class="log-box">
                            {"".join([f"<div>{line}</div>" for line in log_entries])}
                        </div>
                    </div>
                </div>
                
                <p style="text-align: center; color: #444; font-size: 0.8rem; margin-top: 30px;">
                    Uplink: Fortress Security Core @ 127.0.0.1:8000 | Monitoring: Spectre Shadow Engine | Supervisor: Overwatch Active
                </p>
            </div>
        </body>
    </html>
    """
    return html_content

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
