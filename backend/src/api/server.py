from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, Any, List
import asyncio
import json
from src.core.logger import log
from src.core.state import state

app = FastAPI(title="Hyperliquid Trading Bot API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # For development
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ConfigUpdate(BaseModel):
    max_leverage: int = None
    max_position_size_usd: float = None
    max_drawdown_pct: float = None

active_connections: List[WebSocket] = []

@app.get("/api/status")
async def get_status():
    return {
        "is_running": state.is_running,
        "wallet_balance": state.wallet_balance,
        "main_wallet_balance": state.main_wallet_balance,
        "positions_count": len(state.positions),
        "active_orders_count": len(state.active_orders)
    }

@app.get("/api/coins")
async def get_monitored_coins():
    """Returns list of coins being monitored and their current prices."""
    coins_data = {}
    for coin, data in state.market_data.items():
        coins_data[coin] = {
            "price": data.get("price", 0),
            "has_candles": len(data.get("candles", [])) > 0,
            "candle_count": len(data.get("candles", [])),
            "indicators": data.get("indicators", {})
        }
    return {
        "target_coins": ["BTC", "ETH", "SOL", "BNB", "BCH", "ZEC", "XMR", "LTC"],
        "monitored_coins": coins_data,
        "total_monitored": len(coins_data)
    }
    
@app.post("/api/start")
async def start_bot():
    await state.start_bot()
    return {"status": "started"}

@app.post("/api/stop")
async def stop_bot():
    await state.stop_bot()
    return {"status": "stopped"}

@app.post("/api/reset-circuit")
async def reset_circuit_breaker():
    """Reset the circuit breaker to allow trading after failures."""
    state.risk_manager.reset_circuit_breaker()
    return {"status": "circuit_breaker_reset", "bot_running": state.risk_manager.state.is_running}

@app.post("/api/config")
async def update_config(config: ConfigUpdate):
    update_dict = config.dict(exclude_none=True)
    if update_dict:
        await state.update_config(update_dict)
    return {"status": "updated", "config": state.config}

@app.get("/api/trades")
async def get_trades():
    return {
        "trades": [t.dict() for t in state.closed_trades],
        "total_pnl": round(sum(t.pnl for t in state.closed_trades), 6),
        "count": len(state.closed_trades)
    }

@app.get("/api/latency")
async def get_latency():
    """Returns network latency stats per coin."""
    return state.get_latency_stats()

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_connections.append(websocket)
    log.info("Client connected to WS")
    try:
        while True:
            # We just need to keep connection open to stream state outwards
            # Could also receive commands here if desired
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        active_connections.remove(websocket)
        log.info("Client disconnected from WS")

async def state_streamer():
    """Background task to broadcast state to UI periodically."""
    while True:
        try:
            if active_connections:
                payload = {
                    "type": "state_update",
                    "data": {
                        "is_running": state.is_running,
                        "wallet_balance": state.wallet_balance,
                        "positions": {k: v.dict() for k, v in state.positions.items()},
                        "active_orders": {k: v.model_dump() if hasattr(v, 'model_dump') else {"oid": v.oid} for k, v in state.active_orders.items()},
                        "config": state.config,
                        "market_data": state.market_data,
                        "logs": state.logs,
                        "closed_trades": [t.dict() for t in state.closed_trades],
                        "total_pnl": round(sum(t.pnl for t in state.closed_trades), 6)
                    }
                }
                msg = json.dumps(payload)
                for conn in active_connections:
                    await conn.send_text(msg)
                    
        except Exception as e:
            log.error("Error in state streamer", error=str(e))
            
        await asyncio.sleep(1.0) # Stream every second
