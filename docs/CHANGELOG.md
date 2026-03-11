# Changelog

> **⚠️ CRITICAL Rule for AI/Developers:**
> THIS FILE (`CHANGELOG.md`), `README.md`, and `HANDOVER.md` **MUST BE UPDATED ON EVERY CODE CHANGE** to accurately record the modifications made to the repository.

All notable changes to this project will be documented in this file.

## [Unreleased] - 2026-03-09 (v1.2)

### Added
- **Trade History with JSON Persistence**: Added `ClosedTrade` model and `closed_trades` list to `GlobalState` in `state.py`. Trades are recorded on every close (`_close_position`) with entry/exit prices, size, PnL, side, and reason. Exposed via `GET /api/trades` endpoint and streamed via WebSocket. Implemented JSON file persistence:
    - Trades saved to `data/trades.json` immediately when a position closes (no data loss on crash).
    - Trades loaded from JSON on bot startup (survives restarts).
    - Auto-creates `data/` directory if missing.
- **TradeHistory Widget**: New frontend component displaying trade history table with cumulative PnL, win/loss stats, and per-trade details (entry, exit, size, reason).
- **Automatic VWAP-Based Filtering**: The market now automatically dictates trade direction based on price position relative to VWAP (mean reversion):
    - Price > VWAP + 0.5% → Only SHORT allowed (too high, expect pullback)
    - Price < VWAP - 0.5% → Only LONG allowed (too low, expect bounce)
    - Price within ±0.5% of VWAP → Both directions allowed (middle zone)
- **CVD-Based Exit Engine**: Implemented a dynamic trailing stop-loss system in `StrategyModule` triggered on each 1m candle close:
    - Rule 1 — CVD declining (same sign, magnitude dropping) → tighten SL to previous candle POC.
    - Rule 2 — CVD flips sign (hostile to position direction) → tighten SL to current candle POC.
    - Rule 3 — Two consecutive CVD flip candles → market close immediately.
    - Tick-level SL/TP check on every trade event via `_check_sl_tp()`.
- **`Position` model extended**: Added `stop_loss`, `take_profit`, and `side` fields to `state.py` `Position`.
- **`ExecutionGateway.close_position()`**: New method that issues a `market_close` to Hyperliquid (or logs a dryrun skip).
- **Per-Candle POC Overlay**: `ChartWidget` now renders a yellow dashed step-line (`LineType.WithSteps`) over the candlestick chart showing the Point of Control for every historical candle, instead of a single price line for the latest bar only.
- **WebSocket Auto-Reconnect**: `Dashboard.tsx` now reconnects automatically when the backend restarts, using exponential backoff (1 s → 2 s → … → 10 s max).
- **Multi-Pair Support**: The backend now initializes and manages data streams for multiple target coins (BTC, ETH, SOL) concurrently using a comma-separated list in `.env`.
- **Real-Time Telemetry**: Implemented WebSocket streaming of per-symbol market data (candles, CVD, POC, price) to the frontend.
- **Enhanced Live Logging**: Backend now buffers structured logs (including throttled ticker updates) and streams them to the UI in real-time.
- **Candle Data Widget**: Added a `CandleHistory` component to the dashboard for explicit verification of CVD and POC values for each closed candle.
- **Symbol Selector**: Added a UI toggle to switch the chart and logs between different active pairs.
- **Intra-Candle CVD/POC logic**: Finalized the logic for tracking real-time price-delta distributions within the 1m aggregation window.

### Fixed
- **Frontend "Black Screen" Crash**: Implemented React Error Boundaries and robust null-checks in charting and dashboard components to handle partial state updates.
- **Backend Zombie Processes**: Resolved issues where port 8000 would remain occupied by orphan processes during restarts.
- **Chart Initialization**: Fixed an issue where the chart would fail to render or duplicate series when selecting a new symbol.
- **Websocket Stability**: Improved the handshake and error parsing logic for the frontend-backend connection.
- **Log Scroll Logic**: Replaced `scrollIntoView` with manual `scrollTop` management to prevent the dashboard from jumping when new logs arrive.
- **Frontend Crash (Black Screen)**: Added defensive programming (optional chaining, default values) across `Dashboard`, `useStore`, `SystemHealth`, and `ControlPanel` to prevent runtime crashes caused by `undefined` properties during state updates.
- **Latency Tolerance**: Increased latency circuit breaker threshold from 500ms to 5000ms (configurable via `.env`) to avoid constant bot halts in high-latency network environments.
- **Tailwind CSS v4 Migration**: Migrated `index.css` to use `@import "tailwindcss"` and `@theme` block to resolve "unknown utility class" errors in the v4 PostCSS pipeline.
- **Lightweight Charts v5 API Migration**: Migrated `ChartWidget.tsx` and `CandleHistory.tsx` from deprecated `addCandlestickSeries()` / `addAreaSeries()` / `addLineSeries()` / `addHistogramSeries()` to the new unified `chart.addSeries(SeriesDefinition, options)` API introduced in `lightweight-charts` v5.
- **Chart Crash (Duplicate Timestamps)**: Added deduplication and strict ascending-sort in both the backend (`StrategyModule`) and frontend chart components to prevent the `Assertion failed: data must be asc ordered by time` error.
- **Backend Variable Ordering**: Fixed a `ReferenceError` in `StrategyModule.on_market_data` where `closed_1m` and `vwap` were referenced before assignment, crashing all three coin data streams.
- **Chart Disposal Hardening**: Nullified `chartRef.current` after `chart.remove()` to prevent `Object is disposed` errors during React re-renders.
