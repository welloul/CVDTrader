import asyncio
import json
import os
import websockets
import time
from typing import Callable, Coroutine, Dict, Any
from src.core.logger import log
from src.market_data.indicators import IndicatorCompute
from src.market_data.candles import CandleBuilder
from src.market_data.vwap import DailyVWAPTracker

# Hyperliquid WebSocket URLs
TESTNET_WS_URL = "wss://api.hyperliquid-testnet.xyz/ws"
MAINNET_WS_URL = "wss://api.hyperliquid.xyz/ws"

class MarketDataHandler:
    """Handles async WebSocket connection to Hyperliquid for market data."""
    
    # Determine URL based on execution mode
    _exec_mode = os.getenv("EXECUTION_MODE", "dryrun").lower()
    URL = TESTNET_WS_URL if _exec_mode == "testnet" else MAINNET_WS_URL
    
    def __init__(self, coin: str):
        self.coin = coin
        self.callbacks = []
        
        # Core engines
        self.indicators = IndicatorCompute(window_size=100)
        self.vwap = DailyVWAPTracker()
        
        # Per-coin tick size for volume profile binning
        # Must be small enough that POC always falls within candle's [low, high]
        TICK_SIZES = {
            "BTC": 1.0,    # $1 bins for ~$67k asset
            "ETH": 0.10,   # $0.10 bins for ~$2k asset
            "SOL": 0.01,   # $0.01 bins for ~$80 asset
        }
        tick_size = TICK_SIZES.get(coin, 0.01)  # conservative default
        
        # Timeframe Builders
        self.builder_1m = CandleBuilder(timeframe_seconds=60, tick_size=tick_size, history_len=100)
        self.builder_15m = CandleBuilder(timeframe_seconds=900, tick_size=tick_size, history_len=50)
        self.is_running = False
        self.ws = None
        
        # Heartbeat tracking
        self.last_message_time = time.time()
        self.latency_ms = 0.0
        
    def add_callback(self, callback: Callable[[Dict[str, Any]], Coroutine]):
        self.callbacks.append(callback)

    async def connect(self):
        self.is_running = True
        retry_count = 0
        
        while self.is_running:
            try:
                log.info("Connecting to Hyperliquid WebSocket", url=self.URL, coin=self.coin)
                async with websockets.connect(self.URL) as ws:
                    self.ws = ws
                    retry_count = 0
                    
                    # Subscribe to trades
                    sub_msg = {
                        "method": "subscribe",
                        "subscription": {
                            "type": "trades",
                            "coin": self.coin
                        }
                    }
                    await ws.send(json.dumps(sub_msg))
                    
                    log.info("Subscribed to trades", coin=self.coin)
                    
                    # Start heartbeat monitor task
                    monitor_task = asyncio.create_task(self._monitor_heartbeat())
                    
                    try:
                        while self.is_running:
                            msg = await ws.recv()
                            await self._handle_message(msg)
                    except websockets.ConnectionClosed:
                        log.warn("WebSocket connection closed")
                    finally:
                        monitor_task.cancel()
                        
            except Exception as e:
                log.error("WebSocket error", error=str(e), retry=retry_count)
                retry_count += 1
                await asyncio.sleep(min(2 ** retry_count, 30)) # Exponential backoff

    async def _handle_message(self, msg: str):
        # Track heartbeat and measure real processing latency
        receive_time = time.time()
        self.last_message_time = receive_time
        
        data = json.loads(msg)
        
        if "channel" in data and data["channel"] == "trades" and "data" in data:
            trades = data["data"]
            for trade in trades:
                sz = float(trade["sz"])
                px = float(trade["px"])
                is_buy = trade["side"] == "B"
                # Hyperliquid timestamp is in milliseconds
                # Hyperliquid timestamps are in nanoseconds (epoch ns like 1777777777777777777)
                trade_ts_ns = float(trade["time"])
                
                # Convert to appropriate formats
                if trade_ts_ns > 10**15:  # Nanoseconds
                    trade_ts_ms = trade_ts_ns / 1e6  # Convert to milliseconds
                    trade_ts = trade_ts_ns / 1e9  # Convert to seconds
                elif trade_ts_ns > 10**12:  # Milliseconds
                    trade_ts_ms = trade_ts_ns  # Already in milliseconds
                    trade_ts = trade_ts_ns / 1000  # Convert to seconds
                else:  # Already in seconds
                    trade_ts_ms = trade_ts_ns * 1000  # Convert to milliseconds
                    trade_ts = trade_ts_ns
                
                # Calculate network latency (time from trade occurrence to our receipt)
                network_latency_ms = (receive_time - trade_ts) * 1000
                
                # Track latency stats per coin
                if not hasattr(self, 'latency_samples'):
                    self.latency_samples = []
                self.latency_samples.append(network_latency_ms)
                # Keep last 100 samples
                if len(self.latency_samples) > 100:
                    self.latency_samples.pop(0)
                
                # Also track in global state for API access
                from src.core.state import state
                state.update_latency(self.coin, network_latency_ms)
                
                # Update Indicators
                ind_data = self.indicators.process_trade(trade_ts_ms, is_buy, sz, px)
                
                # Update Daily VWAP
                current_vwap = self.vwap.process_trade(trade_ts_ms, sz, px)
                
                # Update Candle Builders
                finished_1m = self.builder_1m.process_trade(trade_ts_ms, px, sz, is_buy)
                finished_15m = self.builder_15m.process_trade(trade_ts_ms, px, sz, is_buy)
                
                # Construct combined market data event
                event = {
                    "type": "market_data",
                    "coin": self.coin,
                    "price": px,
                    "volume": sz,
                    "is_buy": is_buy,
                    "timestamp": trade_ts_ms,
                    "indicators": ind_data,
                    "vwap": current_vwap,
                    "latency_ms": (time.time() - receive_time) * 1000,  # Processing latency
                    "network_latency_ms": network_latency_ms,  # Network latency
                    "closed_candle_1m": finished_1m,
                    "closed_candle_15m": finished_15m
                }
                
                # UI Log for ticker price (throttled by second)
                current_sec = int(trade_ts)
                if not hasattr(self, '_last_log_sec') or current_sec > self._last_log_sec:
                    from src.core.state import state
                    state.add_log("INFO", f"Ticker Update [{self.coin}]: ${px:,.2f}", price=px, coin=self.coin)
                    self._last_log_sec = current_sec
                
                # Dispatch to listeners
                for cb in self.callbacks:
                    await cb(event)

    async def _monitor_heartbeat(self):
        """Monitors freshness of the WebSocket connection."""
        while self.is_running:
            await asyncio.sleep(5)
            idle_time = time.time() - self.last_message_time
            # Use higher threshold for low-volume coins to reduce false warnings
            threshold = 30 if self.coin in ['BTC', 'ETH', 'SOL'] else 60
            if idle_time > threshold:
                log.warn("WebSocket heartbeat stale", idle_time=idle_time, coin=self.coin, threshold=threshold)
                # Consider forcing a reconnect if it gets too high, e.g. closing ws
                if idle_time > 120 and self.ws:
                    await self.ws.close()

    async def stop(self):
        self.is_running = False
        if self.ws:
            await self.ws.close()
        log.info("MarketDataHandler stopped")
