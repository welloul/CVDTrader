# Project Handover Document

> **⚠️ CRITICAL Rules for AI/Developers — READ BEFORE MAKING ANY CHANGES:**
>
> 1. THIS FILE (`HANDOVER.md`), `README.md`, and `CHANGELOG.md` **MUST BE UPDATED ON EVERY CODE CHANGE** to accurately reflect the current state, architecture, and history of the project.
>
> 2. **EVERY feature, strategy, indicator, execution flow, or component MUST be documented in the `/docs` folder.** When adding a new feature, create or update a `.md` file in `/docs` that explains:
>    - What it does
>    - How it calculates / operates
>    - How it integrates with the rest of the system
>    - Any known limitations or configuration options
>
> **Current documentation files in `/docs`:**
> - [`docs/architecture.md`](docs/architecture.md) — System architecture overview
> - [`docs/setup_guide.md`](docs/setup_guide.md) — Installation and configuration
> - [`docs/CVD-POC.md`](docs/CVD-POC.md) — Delta-POC Reversal strategy: CVD/POC calculation, signal logic, entry, and CVD-based exit engine
> - [`docs/strategy_delta_poc.md`](docs/strategy_delta_poc.md) — Original strategy design notes (superseded by CVD-POC.md for implementation detail)

## Current State of the Project
**Status:** Alpha/Development
The bot is fully scaffolded. The backend event-loop is functional, streaming data, building custom OHLCV candles, computing Volume Profiles (POC), tracking Daily VWAP, and running the "Delta-POC" strategy logic. The frontend can successfully connect via WebSocket to visualize the state, configuration, and execution mode.

## System Components

### 1. Data Engines (`backend/src/market_data/`)
- **`handler.py`**: Manages the main Hyperliquid WebSocket connection. Subscribes to `trades` and dispatches events.
- **`candles.py`**: Custom aggregator (`CandleBuilder`) that takes raw ticks and builds strict 1m and 15m OHLCV bars.
- **`profile.py`**: Calculates the precise Point of Control (POC) for a given candle time bucket (`VolumeProfileBuilder`).
- **`vwap.py`**: Tracks the continuous Volume-Weighted Average Price resetting daily at 00:00 UTC.
- **`indicators.py`**: Maintains rolling buffers to calculate Cumulative Volume Delta (CVD) and Relative Volume (RVOL).

### 2. Execution & Risk (`backend/src/execution/` and `backend/src/risk/`)
- **`gateway.py`**: Sends Post-Only (Alo) Limit orders to the exchange. Checks `EXECUTION_MODE` to intercept and mock `dryrun` orders.
- **`ttl.py`**: Time-to-Live engine (`OrderTTLTracker`). Cancels limit orders placed at POC if they are not filled within 5 minutes.
- **`manager.py`**: Validates max leverage, max position sizing, and tracks API latency for circuit breaking.

### 3. State & Control (`backend/src/core/` and `backend/src/api/`)
- **`state.py`**: Holds `GlobalState` (Positions, Wallet Balance, Config). Syncs reality with the Hyperliquid API on startup.
- **`server.py`**: FastAPI endpoints. `/ws` streams the state to the React frontend. REST handles config changes.

### 4. Strategy (`backend/src/strategy/`)
- **`module.py`**: Core `StrategyModule`. Subscribes to the `MarketDataHandler`. Implements **Delta-POC Reversal** with **automatic VWAP-based filtering** (mean reversion):
  - **Price > VWAP + 0.5%** → Only SHORT allowed (too high, expect pullback)
  - **Price < VWAP - 0.5%** → Only LONG allowed (too low, expect bounce)
  - **Price within ±0.5% of VWAP** → Both directions allowed (middle zone)

### 5. Frontend (`frontend/`)
- React + Vite + TS + Tailwind v4 (`@theme` block in `index.css`).
- Uses `Zustand` for global state management.
- Dashboard with Bento Grid layout featuring:
  - `ChartWidget`: TradingView Lightweight Charts v5 (Candlestick + CVD Histogram + **per-candle POC step-line** overlay).
  - `CandleHistory`: CVD & POC Verification chart (Area price, dashed POC line, CVD histogram) for validating indicator accuracy.
  - `SystemHealth`: WS status, latency, strategy state.
  - `ControlPanel`: Start/Stop, risk parameter adjustments.
  - `LiveLogs`: Real-time execution and ticker update log stream.
  - `TradeHistory`: Trade history table with cumulative PnL, win/loss stats, and per-trade details (entry, exit, size, reason). Streamed live via WebSocket.
  - **Symbol Selector**: BTC / ETH / SOL toggle in the header.
- **Important**: Uses `lightweight-charts` v5 unified `addSeries()` API — do **not** use the deprecated `addCandlestickSeries()` etc.

## Known Issues / Next Steps
1. ~~WebSocket auto-reconnect~~ ✅ **Fixed**: `Dashboard.tsx` now reconnects automatically with exponential backoff (1 s → 10 s max) when the backend restarts.
2. ~~No automated exit~~ ✅ **Fixed**: CVD-based trailing SL engine implemented in `StrategyModule` (see Exit Engine section in class docstring). Position model now carries `stop_loss`, `take_profit`, `side`.
3. ~~No trade history / PnL tracking~~ ✅ **Fixed**: Added `ClosedTrade` model + `closed_trades` list in `GlobalState`. Trades are recorded on every close (`_close_position`) with entry/exit prices, size, PnL, and reason. Exposed via `GET /api/trades` and streamed via WebSocket. Frontend now has a `TradeHistory` widget showing cumulative PnL, win/loss stats, and per-trade details. **JSON persistence** added: trades are saved to `data/trades.json` immediately on close and loaded on startup, surviving bot restarts.
4. Hyperliquid WS connection: retries on error but lacks exponential backoff (backend `handler.py`).
5. Order tracking via `userData` websocket needs to be wired to update `GlobalState` in real-time (currently synced at startup only).
6. Connect the frontend `ControlPanel` buttons (Start/Stop, Update Risk) to the backend REST API endpoints.
7. Historical data pre-fetching: The bot currently waits for 1m candles to close organically; pre-fetching initial history via REST would speed startup.
8. The `CandleHistory` and `ChartWidget` charts both deduplicate incoming candle data on the frontend — this is a safety net but the backend also deduplicates in `StrategyModule.on_market_data`.
