import asyncio
import time
from typing import Dict
from src.core.logger import log
from src.core.state import GlobalState
from src.execution.gateway import ExecutionGateway

class OrderTTLTracker:
    """
    Monitors active limit orders placed by the strategy.
    Cancels them if they remain unfilled past the TTL (Time-to-Live).
    """
    def __init__(self, state: GlobalState, gateway: ExecutionGateway):
        self.state = state
        self.gateway = gateway
        self.tracked_orders: Dict[int, float] = {} # Dict mapping OID -> timestamp of expiry
        self.is_running = False

    async def start(self):
        self.is_running = True
        log.info("Starting Order TTL Tracker")
        while self.is_running:
            await self._check_expiries()
            await asyncio.sleep(1) # Check every second

    async def stop(self):
        self.is_running = False

    def track_order(self, oid: int, ttl_seconds: int = 300):
        """Standard TTL is 5 minutes (300 seconds) for Delta-POC."""
        expiry = time.time() + ttl_seconds
        self.tracked_orders[oid] = expiry
        log.info("Tracking Order for TTL", oid=oid, ttl=ttl_seconds)

    async def _check_expiries(self):
        """Evaluates tracked orders against current time and cancels if expired."""
        now = time.time()
        expired_oids = []
        
        for oid, expiry in list(self.tracked_orders.items()):
            # Important: Check if order even exists in global state anymore
            # Might have been filled or manually cancelled
            if oid not in self.state.active_orders:
                expired_oids.append(oid)
                continue
                
            if now > expiry:
                log.info("Order reached TTL Expiry, cancelling", oid=oid)
                
                # Active order found and expired. Cancel it.
                order = self.state.active_orders[oid]
                
                # Use gateway to cancel (requires gateway implementation of cancel_order)
                if self.gateway.exchange:
                    try:
                        # Hyperliquid 'cancel' command format usually needs coin and oid
                        result = self.gateway.exchange.cancel(order.coin, oid)
                        log.info("Cancellation result", result=result)
                    except Exception as e:
                        log.error("Failed to cancel expired order", oid=oid, error=str(e))
                
                expired_oids.append(oid)
                
        # Cleanup
        for oid in expired_oids:
            if oid in self.tracked_orders:
                del self.tracked_orders[oid]
