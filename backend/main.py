import asyncio
import os
import uvicorn
from dotenv import load_dotenv

from hyperliquid.exchange import Exchange
from hyperliquid.info import Info
from hyperliquid.utils import constants
import eth_account

from src.core.logger import log
from src.core.state import state
from src.core.rounding import RoundingUtil
from src.market_data.handler import MarketDataHandler
from src.risk.manager import risk_manager
from src.execution.gateway import ExecutionGateway
from src.strategy.module import StrategyModule
from src.api.server import app, state_streamer

# Load environment variables
load_dotenv()

async def start_bot_loop():
    """Initializes and runs the main bot components."""
    
    # 1. Setup Execution Mode and Strategy
    execution_mode = os.getenv("EXECUTION_MODE", "dryrun").lower()
    if execution_mode not in ["live", "testnet", "dryrun"]:
        log.warn("Invalid EXECUTION_MODE, defaulting to dryrun")
        execution_mode = "dryrun"
        
    active_strategy = os.getenv("ACTIVE_STRATEGY", "delta_poc")
    max_latency_ms = int(os.getenv("MAX_LATENCY_MS", "5000"))
        
    await state.update_config({
        "execution_mode": execution_mode,
        "active_strategy": active_strategy,
        "max_latency_ms": max_latency_ms
    })
    
    # 2. Setup Hyperliquid SDK Clients
    secret_key = os.getenv("HYPERLIQUID_SECRET_KEY", "")
    wallet_address = os.getenv("HYPERLIQUID_WALLET_ADDRESS", "")
    
    api_url = constants.TESTNET_API_URL if execution_mode == "testnet" else constants.MAINNET_API_URL
    log.info("Initializing Hyperliquid client", mode=execution_mode, url=api_url)
    
    if not secret_key or not wallet_address:
        log.warn("HYPERLIQUID_SECRET_KEY or HYPERLIQUID_WALLET_ADDRESS not found in .env. Starting in read-only mode.")
        account = None
        exchange = None
    else:
        account = eth_account.Account.from_key(secret_key)
        exchange = Exchange(account, api_url)
        
    info = Info(api_url, skip_ws=True)
    
    # Fetch exchange metadata for rounding
    log.info("Fetching exchange metadata...")
    meta = info.meta()
    rounding_util = RoundingUtil(meta)
    
    # 2. Sync Initial State
    log.info("Syncing initial state...")
    if wallet_address:
        await state.sync_state(info, wallet_address)
        
    # 3. Initialize Strategy & Execution
    gateway = ExecutionGateway(exchange, rounding_util) if exchange else None
    if not gateway:
        log.warn("Execution gateway is disabled (read-only mode).")
        
    strategy = StrategyModule(state, gateway, risk_manager)
    
    # 4. Initialize Market Data Handlers for all configured coins
    target_coins_str = os.getenv("TARGET_COINS", "BTC,ETH,SOL")
    target_coins = [c.strip() for c in target_coins_str.split(",") if c.strip()]
    
    handlers = []
    md_tasks = []
    
    for coin in target_coins:
        log.info(f"Initializing MarketDataHandler for {coin}")
        md_handler = MarketDataHandler(coin)
        md_handler.add_callback(strategy.on_market_data)
        
        handlers.append(md_handler)
        md_tasks.append(asyncio.create_task(md_handler.connect()))


    # 5. Start background tasks
    # Start the state streamer for the frontend UI
    asyncio.create_task(state_streamer())
    
    # Wait for all market data tasks to run
    try:
        await asyncio.gather(*md_tasks)
    except asyncio.CancelledError:
        log.info("Bot loop cancelled")
    finally:
        for handler in handlers:
            await handler.stop()

@app.on_event("startup")
async def startup_event():
    log.info("Starting up FastAPI application")
    # Launch bot loop in the background
    asyncio.create_task(start_bot_loop())

if __name__ == "__main__":
    log.info("Starting server...")
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
