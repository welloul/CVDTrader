from typing import Dict, Any, List
from pydantic import BaseModel, Field
import asyncio
import datetime
import json
import os
from src.core.logger import log

TRADES_FILE = "data/trades.json"

class ClosedTrade(BaseModel):
    id: str
    coin: str
    side: str          # "LONG" or "SHORT"
    size: float
    entry_price: float
    exit_price: float
    pnl: float
    reason: str
    opened_at: str     # ISO timestamp
    closed_at: str     # ISO timestamp

class Position(BaseModel):
    coin: str
    size: float
    entry_price: float
    leverage: float
    unrealized_pnl: float
    stop_loss: float = 0.0
    take_profit: float = 0.0
    side: str = ""  # "LONG" or "SHORT"
    opened_at: str = ""  # ISO timestamp

class ActiveOrder(BaseModel):
    oid: int
    coin: str
    is_buy: bool
    sz: float
    limit_px: float
    order_type: str = "limit"

class GlobalState:
    """Manages bot state, positions, and active orders."""
    def __init__(self):
        self.is_running: bool = False
        self.config: Dict[str, Any] = {
            "max_leverage": 5,
            "max_position_size_usd": 1000,
            "max_drawdown_pct": 5.0,
            "execution_mode": "dryrun", # live, testnet, dryrun
            "active_strategy": "delta_poc",
            "max_latency_ms": 5000
        }
        self.positions: Dict[str, Position] = {}
        self.active_orders: Dict[int, ActiveOrder] = {}
        self.closed_trades: List[ClosedTrade] = []
        
        # Per-coin data series for charting (candles, indicators)
        # Structure: { "BTC": { "candles": [...], "cvd": [...] } }
        self.market_data: Dict[str, Dict[str, List[Any]]] = {}
        
        self.wallet_balance: float = 0.0
        self.logs: List[Dict[str, Any]] = [] # Buffer for UI logs
        
        # Synchronization lock
        self._lock = asyncio.Lock()
        
        # Load persisted trades on startup
        self._load_trades()

    def add_log(self, level: str, message: str, **kwargs):
        """Adds a log entry to the UI buffer."""
        import datetime
        entry = {
            "timestamp": datetime.datetime.now().isoformat(),
            "level": level,
            "message": message,
            **kwargs
        }
        self.logs.append(entry)
        if len(self.logs) > 50:
            self.logs.pop(0)

    def _load_trades(self):
        """Load closed trades from JSON file if it exists."""
        if not os.path.exists(TRADES_FILE):
            return
        try:
            with open(TRADES_FILE, "r") as f:
                data = json.load(f)
                for t in data:
                    self.closed_trades.append(ClosedTrade(**t))
            log.info(f"Loaded {len(self.closed_trades)} trades from {TRADES_FILE}")
        except Exception as e:
            log.error(f"Failed to load trades: {e}")
    
    def _save_trades(self):
        """Save closed trades to JSON file."""
        os.makedirs(os.path.dirname(TRADES_FILE), exist_ok=True)
        try:
            data = [t.model_dump() for t in self.closed_trades]
            with open(TRADES_FILE, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            log.error(f"Failed to save trades: {e}")

    async def update_config(self, new_config: Dict[str, Any]):
        async with self._lock:
            self.config.update(new_config)
            log.info("Configuration updated", new_config=self.config)

    async def start_bot(self):
        async with self._lock:
            self.is_running = True
            log.info("Bot started via Command & Control")

    async def stop_bot(self):
        async with self._lock:
            self.is_running = False
            log.info("Bot stopped via Command & Control")
            
    async def sync_state(self, info_client: Any, address: str):
        """Reconciles state with Hyperliquid API."""
        async with self._lock:
            try:
                # In dryrun, we might still want to fetch real state to simulate, 
                # or just start from 0 if we mock. We'll fetch real state if available.
                user_state = info_client.user_state(address)
                
                # Update wallet balance
                self.wallet_balance = float(user_state["marginSummary"]["accountValue"])
                
                # Update positions
                self.positions.clear()
                for pos in user_state["assetPositions"]:
                    pos_info = pos["position"]
                    coin = pos_info["coin"]
                    sz = float(pos_info["szi"])
                    
                    if sz != 0:
                        self.positions[coin] = Position(
                            coin=coin,
                            size=sz,
                            entry_price=float(pos_info["entryPx"]),
                            leverage=float(pos_info["leverage"]["value"]),
                            unrealized_pnl=float(pos_info["unrealizedPnl"])
                        )
                
                # Update active orders
                open_orders = info_client.open_orders(address)
                self.active_orders.clear()
                for order in open_orders:
                    self.active_orders[order["oid"]] = ActiveOrder(
                        oid=order["oid"],
                        coin=order["coin"],
                        is_buy=order["side"] == "B",
                        sz=float(order["sz"]),
                        limit_px=float(order["limitPx"])
                    )
                
                log.info(
                    "State synchronized with Hyperliquid", 
                    wallet_balance=self.wallet_balance,
                    open_positions=len(self.positions),
                    active_orders=len(self.active_orders),
                    mode=self.config["execution_mode"]
                )
                
            except Exception as e:
                log.error("Failed to sync state", error=str(e))

# Singleton instance
state = GlobalState()
