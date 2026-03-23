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
from src.execution.ttl import OrderTTLTracker
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
    main_wallet_address = os.getenv("HYPERLIQUID_MAIN_WALLET_ADDRESS", "")
    
    # Debug: Print loaded addresses
    log.info("Loaded wallet addresses from .env", 
              wallet_address=wallet_address, 
              main_wallet_address=main_wallet_address)
    
    api_url = constants.TESTNET_API_URL if execution_mode == "testnet" else constants.MAINNET_API_URL
    log.info("Initializing Hyperliquid client", mode=execution_mode, url=api_url)
    
    if not secret_key or not wallet_address:
        log.warn("HYPERLIQUID_SECRET_KEY or HYPERLIQUID_WALLET_ADDRESS not found in .env. Starting in read-only mode.")
        account = None
        exchange = None
    else:
        account = eth_account.Account.from_key(secret_key)
        try:
            exchange = Exchange(account, api_url)
        except Exception as e:
            log.error("Failed to initialize Exchange client", error=str(e))
            log.warn("Falling back to read-only mode")
            exchange = None
    
    # Use Info client for market data (no auth needed for public data)
    try:
        info = Info(api_url, skip_ws=True)
    except Exception as e:
        log.error("Failed to initialize Info client", error=str(e))
        log.warn("Using minimal Info client for market data only")
        info = None
    
    # Fetch exchange metadata for rounding
    if info:
        log.info("Fetching exchange metadata...")
        meta = info.meta()
    else:
        log.warn("No Info client available, using default metadata")
        meta = None
    rounding_util = RoundingUtil(meta)
    
    # 2. Sync Initial State
    log.info("Syncing initial state...")
    if wallet_address:
        await state.sync_state(info, wallet_address)
    
    # 3. Fetch main wallet balance if configured
    if main_wallet_address and main_wallet_address != wallet_address:
        log.info("Fetching main wallet balance...", main_wallet=main_wallet_address)
        await state.sync_main_wallet_balance(info, main_wallet_address)
        
    # 3. Initialize Strategy & Execution
    # Initialize TTL tracker for stale order cancellation FIRST (before gateway)
    ttl_tracker = None
    gateway = None
    if exchange:
        ttl_tracker = OrderTTLTracker(state, None)  # Will set gateway after gateway is created
        gateway = ExecutionGateway(exchange, rounding_util, ttl_tracker)
        # Now set the gateway on the ttl_tracker
        ttl_tracker.gateway = gateway
        asyncio.create_task(ttl_tracker.start())
        log.info("Order TTL Tracker started (2 min default)")
    
    if not gateway:
        log.warn("Execution gateway is disabled (read-only mode).")
    
    strategy = StrategyModule(state, gateway, risk_manager, ttl_tracker)
    
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
    
    # Start periodic state sync (every 10 seconds to keep active orders in sync)
    async def periodic_state_sync():
        while True:
            try:
                await asyncio.sleep(10)  # Sync every 10 seconds
                if wallet_address and info:
                    await state.sync_state(info, wallet_address)
                    log.info("Periodic state sync completed")
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error("Periodic sync failed", error=str(e))
    
    asyncio.create_task(periodic_state_sync())
    
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
