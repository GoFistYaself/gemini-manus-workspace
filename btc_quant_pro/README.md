# BTC Quant Pro Framework

## Overview
A modular, standardized Python framework for backtesting cryptocurrency trading strategies. 

## Features
- **Standardized Data Loading:** Multi-index flattening and date normalization.
- **Confluence Engine:** Combines EMA trends, Fibonacci levels, RSI, and Volume.
- **Dynamic SL/TP:** ATR-based risk management.
- **Modular Design:** Separate components for Indicators, Signals, Backtesting, and Metrics.

## Project Structure
- `src/core/`: Core trading logic (data, indicators, signals, backtest).
- `src/utils/`: Support logic (metrics, plotting).
- `tests/`: Unit tests for core components.
- `main.py`: Entry point for running the strategy.

## Getting Started
1. Install dependencies: `pip install -r requirements.txt`
2. Run the strategy: `python main.py`

## API Documentation
### `DataLoader`
`fetch_ohlcv(symbol, period, interval)`: Returns cleaned OHLCV data.

### `IndicatorCalculator`
`apply_indicators(df)`: Adds EMA, Fibonacci, RSI, and ATR to the dataframe.

### `SignalEngine`
`generate_signals(df)`: Applies trading logic and returns a Signal column (1, -1, 0).

## Live Trading on Coinbase
To switch from Paper Trading to Live Trading mode, follow these steps:

### 1. API Configuration
1. Log in to **Coinbase Advanced Trade**.
2. Navigate to **Settings > API** and create a new API key with **Trade** permissions.
3. Copy the **API Key** and **API Secret**.

### 2. Environment Setup
Update your `.env` file in the project root with your credentials:
```ini
COINBASE_API_KEY="your_api_key_here"
COINBASE_API_SECRET="your_api_secret_here"
```

### 3. Execution
Run the bot with the `--live` flag to enable real-money trading:
```powershell
python run_bot.py --live
```
**Safety Confirmation:** You will be prompted to type `LIVE` to confirm. This ensures that live trading is an intentional action.

## Error Handling
The bot includes strict credential validation. If `COINBASE_API_KEY` or `COINBASE_API_SECRET` are missing, the bot will abort initialization and provide a clear error message.
