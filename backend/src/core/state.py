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
    reason: str        # Exit reason (e.g., "TP hit", "SL hit @ 86.89", "CVD flip SL")
    entry_reason: str = ""  # Why the trade was opened
    sl_modifications: List[str] = []  # Log of SL changes with reasons
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
    breakeven: float = 0.0  # Fee-adjusted breakeven price
    side: str = ""  # "LONG" or "SHORT"
    opened_at: str = ""  # ISO timestamp
    # Trade explainers
    entry_reason: str = ""  # Why the trade was opened (e.g., "Exhaustion signal", "CVD divergence")
    sl_modifications: List[str] = Field(default_factory=list)  # Log of SL changes with reasons
    # Partial TP tracking
    tp_50_hit: bool = False  # True if 50% was closed at TP
    trailing_sl: float = 0.0  # Trailing SL for remaining 50%
    original_tp: float = 0.0  # Original TP price for reference

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
            "max_position_size_usd": 50,
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
        self.main_wallet_balance: float = 0.0  # Main wallet balance (for API agents)
        self.logs: List[Dict[str, Any]] = [] # Buffer for UI logs
        
        # Network latency tracking per coin
        # Structure: { "BTC": [latency_ms, ...] }
        self.latency_by_coin: Dict[str, List[float]] = {}
        
        # Synchronization lock
        self._lock = asyncio.Lock()
        
        # Load persisted trades on startup
        self._load_trades()

    def update_latency(self, coin: str, latency_ms: float):
        """Track network latency for a coin."""
        if coin not in self.latency_by_coin:
            self.latency_by_coin[coin] = []
        self.latency_by_coin[coin].append(latency_ms)
        # Keep last 100 samples per coin
        if len(self.latency_by_coin[coin]) > 100:
            self.latency_by_coin[coin].pop(0)

    def get_latency_stats(self) -> Dict[str, Dict[str, float]]:
        """Get latency stats (avg, min, max) per coin, filtered to show actual network latency.
        
        Note: Values include clock skew between local machine and Hyperliquid servers.
        The consistent offset (around -28000ms) represents clock difference, not actual latency.
        """
        stats = {}
        for coin, samples in self.latency_by_coin.items():
            if not samples:
                continue
            # Filter out extreme outliers (likely historical backfill)
            # Keep values between -50000 and 50000 ms
            filtered = [s for s in samples if -50000 < s < 50000]
            if not filtered:
                continue
            # Calculate median to find clock skew
            sorted_vals = sorted(filtered)
            median = sorted_vals[len(sorted_vals) // 2]
            # Show both raw average and "corrected" (subtracting median offset)
            avg = sum(filtered) / len(filtered)
            stats[coin] = {
                "avg_ms": round(avg, 2),
                "min_ms": round(min(filtered), 2),
                "max_ms": round(max(filtered), 2),
                "clock_offset_ms": round(median, 2),  # Clock skew from Hyperliquid
                "samples": len(filtered)
            }
        return stats

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
        """Start the bot and reset circuit breaker."""
        async with self._lock:
            self.is_running = True
            # Reset circuit breaker when starting the bot
            # Import the singleton directly
            from src.risk.manager import risk_manager as rm
            rm.circuit_breaker_active = False
            rm.consecutive_failures = 0
            log.info("Circuit breaker reset on bot start")
            log.info("Bot started via Command & Control")

    async def stop_bot(self):
        async with self._lock:
            self.is_running = False
            log.info("Bot stopped via Command & Control")
            
    async def sync_state(self, info_client: Any, address: str):
        """Reconciles state with Hyperliquid API."""
        async with self._lock:
            try:
                # Debug: Log the address being used
                log.info("Syncing state with address", address=address)
                
                # In dryrun, we might still want to fetch real state to simulate, 
                # or just start from 0 if we mock. We'll fetch real state if available.
                user_state = info_client.user_state(address)
                
                # Debug: Log raw response structure
                log.info("User state response keys", keys=list(user_state.keys()) if isinstance(user_state, dict) else "not dict")
                
                # Update wallet balance (combined: perp margin + spot USDC)
                perp_balance = float(user_state["marginSummary"]["accountValue"])
                
                # Get spot wallet balance (USDC)
                try:
                    spot_state = info_client.spot_user_state(address)
                    spot_balance = 0.0
                    for bal in spot_state.get("balances", []):
                        if bal.get("coin") == "USDC":
                            spot_balance = float(bal.get("total", "0.0"))
                            break
                    log.info("Spot balance fetched", spot_balance=spot_balance)
                except Exception as e:
                    log.warning("Failed to fetch spot balance", error=str(e))
                    spot_balance = 0.0
                
                # Total wallet balance = perp margin + spot USDC
                self.wallet_balance = perp_balance + spot_balance
                log.info("Wallet balance updated", perp_balance=perp_balance, spot_balance=spot_balance, total=self.wallet_balance)
                
                # Debug: Log assetPositions
                asset_positions = user_state.get("assetPositions", [])
                log.info("Asset positions raw", count=len(asset_positions), data=str(asset_positions)[:500])
                
                # Update positions - preserve existing SL/TP if position already exists
                new_positions = {}
                for pos in user_state["assetPositions"]:
                    pos_info = pos["position"]
                    coin = pos_info["coin"]
                    sz = float(pos_info["szi"])
                    
                    if sz != 0:
                        entry_px = float(pos_info["entryPx"])
                        
                        # Preserve existing SL/TP if position already exists with those values
                        existing_pos = self.positions.get(coin)
                        stop_loss = existing_pos.stop_loss if existing_pos and existing_pos.stop_loss > 0 else 0.0
                        take_profit = existing_pos.take_profit if existing_pos and existing_pos.take_profit > 0 else 0.0
                        tp_50_hit = existing_pos.tp_50_hit if existing_pos else False
                        trailing_sl = existing_pos.trailing_sl if existing_pos else 0.0
                        original_tp = existing_pos.original_tp if existing_pos else 0.0
                        
                        new_positions[coin] = Position(
                            coin=coin,
                            size=sz,
                            entry_price=entry_px,
                            leverage=float(pos_info["leverage"]["value"]),
                            unrealized_pnl=float(pos_info["unrealizedPnl"]),
                            breakeven=entry_px,
                            stop_loss=stop_loss,
                            take_profit=take_profit,
                            tp_50_hit=tp_50_hit,
                            trailing_sl=trailing_sl,
                            original_tp=original_tp
                        )
                
                # Always clear and update positions from exchange - use ONLY exchange data
                self.positions.clear()
                self.positions.update(new_positions)
                
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

    async def sync_main_wallet_balance(self, info_client: Any, main_wallet_address: str):
        """Fetches the main wallet balance (for API agent configuration)."""
        if not info_client or not main_wallet_address:
            return
        try:
            user_state = info_client.user_state(main_wallet_address)
            log.info("Main wallet state response", user_state=str(user_state)[:500])
            self.main_wallet_balance = float(user_state["marginSummary"]["accountValue"])
            log.info(
                "Main wallet balance fetched",
                main_wallet_balance=self.main_wallet_balance,
                main_wallet=main_wallet_address
            )
        except Exception as e:
            log.error("Failed to fetch main wallet balance", error=str(e))

# Singleton instance
state = GlobalState()
