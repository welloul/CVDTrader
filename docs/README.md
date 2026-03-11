# CVDTrader: Hyperliquid Auto-Trader

A production-ready, asynchronous Python trading bot on Hyperliquid with a FastAPI backend and a React (Vite + TypeScript) frontend dashboard.

> **⚠️ CRITICAL Rule for AI/Developers:**
> THIS FILE (`README.md`), `HANDOVER.md`, and `CHANGELOG.md` **MUST BE UPDATED ON EVERY CODE CHANGE** to accurately reflect the current state, architecture, and history of the project.

## Architecture Overview

This project is divided into two main components:
1. **Backend (`/backend`)**: Python/FastAPI async application that connects to Hyperliquid via WebSocket for market data, manages global trading state, evaluates strategies (like Delta-POC Reversal), and executes orders with a robust risk/TTL engine. **Supports multi-pair monitoring (BTC, ETH, SOL) concurrently.**
2. **Frontend (`/frontend`)**: React (Vite+TS) application providing a high-density Bento Grid dashboard with TradingView Lightweight Charts v5, system health metrics, live order logs, and command & control over the bot's risk parameters. **Features a real-time CVD/POC verification chart and symbol switching (BTC/ETH/SOL).**
   - *Note: Uses Tailwind CSS v4 with `@theme` block in `src/index.css`. Charts use `lightweight-charts` v5 unified `addSeries()` API.*

## Key Features
- **Multi-Pair Monitoring**: Concurrent market data handlers for BTC, ETH, and SOL.
- **Real-Time Visuals**: Live CVD (Cumulative Volume Delta) histogram and per-candle POC (Point of Control) step-line overlay on Candlestick charts.
- **CVD/POC Verification Chart**: Dedicated chart widget showing Close price (area), POC (dashed line), and CVD (histogram) per candle for indicator validation.
- **Streaming Logs**: Real-time ticker price updates and execution logs streamed via WebSocket.
- **Risk Circuit Breakers**: Automatic halt on high latency or consecutive execution failures.

## Current Strategy: Delta-POC Reversal
The bot currently trades Exhaustion/Absorption setups by looking for high-volume stalling patterns inside 1-minute candles, filtering direction using a Daily VWAP, and executing strictly passive (Post-Only) limit orders directly at the recent Point of Control (POC).

## Getting Started

### Clone the Repository
```bash
git clone https://github.com/welloul/CVDTrader.git
cd CVDTrader
```

### Backend Setup
```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Copy the example environment file and add your credentials
cp .env.example .env
```
To run the backend: `uvicorn main:app --reload` (or `python main.py` if directly executing).

### Frontend Setup
```bash
cd frontend
npm install
```
To run the frontend: `npm run dev`

## Execution Modes
Set `EXECUTION_MODE` in the backend `.env` file to one of the following:
- `dryrun`: Connects to Mainnet market data but skips actual order execution, simulating success. (Default)
- `testnet`: Connects to Hyperliquid Testnet API and executes real testnet orders.
- `live`: Connects to Hyperliquid Mainnet and executes real orders with real funds.

Set `ACTIVE_STRATEGY=delta_poc` to define the baseline strategy to execute.
