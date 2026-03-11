# System Architecture

The CVDTrader bot is designed as a high-performance, event-driven trading system optimized for the Hyperliquid exchange. It leverages asynchronous programming in Python to minimize latency and a modern React frontend for real-time monitoring.

## 1. Backend Architecture (Python/FastAPI)

The backend is built using `asyncio` to handle concurrent WebSocket streams and API requests efficiently.

### Core Components

- **Global State (`src/core/state.py`)**: Centralized repository for the bot's current status, positions, active orders, and configuration. It ensures consistency across all modules.
- **Market Data Handler (`src/market_data/handler.py`)**: Manages the WebSocket connection to Hyperliquid. It subscribes to trade data and feeds it into the various data engines.
- **Data Engines**:
    - **`CandleBuilder`**: Aggregates raw trades into time-based bars (1m, 15m).
    - **`VolumeProfileBuilder`**: Calculates the Point of Control (POC) within each candle.
    - **`DailyVWAPTracker`**: Computes the session-specific Volume-Weighted Average Price.
    - **`IndicatorCompute`**: Calculates technical metrics like CVD and RVOL.
- **Risk Manager (`src/risk/manager.py`)**: Enforces safety constraints such as maximum leverage, position size limits, and account drawdown protections. It also includes a circuit breaker for high latency.
- **Execution Gateway (`src/execution/gateway.py`)**: Handles order placement, specifically focusing on "Post-Only" limit orders to ensure maker status.
- **Order TTL Tracker (`src/execution/ttl.py`)**: A background worker that automatically cancels unfilled entry orders after a specified duration.
- **Strategy Module (`src/strategy/module.py`)**: The brain of the bot. it listens to market data events and evaluates entry/exit signals based on the active strategy.

## 2. Frontend Architecture (React/Vite)

The frontend is a lightweight, responsive dashboard designed for high-density information display.

- **State Management**: Uses `zustand` for a reactive and easy-to-manage application state, synchronized with the backend via WebSockets.
- **UI Framework**: Tailwind CSS for rapid, modern styling with a custom "Hyperliquid" inspired dark theme.
- **Visualization**: Integration with TradingView's `lightweight-charts` for professional-grade price and volume delta charting.
- **Components**:
    - **Dashboard**: Main layout orchestrating all widgets.
    - **ControlPanel**: Interface for manual bot control and risk parameter adjustment.
    - **SystemHealth**: Real-time telemetry on connection status and latency.
    - **LiveLogs**: Streaming display of backend application logs.

## 3. Communication Protocol

- **WebSockets**: The primary channel for real-time state updates from the backend to the frontend.
- **REST API**: Used for command and control actions, such as starting/stopping the bot or updating configuration parameters.
