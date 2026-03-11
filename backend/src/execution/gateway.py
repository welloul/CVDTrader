import asyncio
from typing import Dict, Any, Optional
from hyperliquid.exchange import Exchange
from src.core.logger import log
from src.core.rounding import RoundingUtil
from src.risk.manager import risk_manager

class ExecutionGateway:
    """Handles execution logic on Hyperliquid."""
    
    def __init__(self, exchange_client: Exchange, rounding_util: RoundingUtil):
        self.exchange = exchange_client
        self.rounding = rounding_util

    async def execute_limit_order(self, coin: str, is_buy: bool, sz: float, limit_px: float) -> Optional[Dict[str, Any]]:
        """
        Executes a Post-Only Limit Order.
        Ensures sizes and prices are rounded according to Hyperliquid spec before sending.
        """
        if not risk_manager.check_pre_trade(coin, sz, limit_px):
            return None
            
        rounded_sz_str = self.rounding.round_size(coin, sz)
        rounded_sz = float(rounded_sz_str)
        
        rounded_px_str = self.rounding.round_price(coin, limit_px)
        rounded_px = float(rounded_px_str)
        
        if rounded_sz <= 0:
            log.error("Rounded size is 0 or negative", original_sz=sz)
            return None

        # Format string values strictly for API by stripping trailing zeros
        formatted_sz = self.rounding.format_for_api(rounded_sz)
        formatted_px = self.rounding.format_for_api(rounded_px)
        
        mode = risk_manager.state.config.get("execution_mode", "dryrun")

        log.info(
            f"[{mode.upper()}] Executing Post-Only Limit Order", 
            coin=coin, 
            is_buy=is_buy, 
            sz=formatted_sz, 
            limit_px=formatted_px
        )

        if mode == "dryrun":
            log.info("Dryrun mode: Order skipped", coin=coin)
            # Simulate success in dryrun
            risk_manager.record_order_result(True)
            return {"status": "ok", "response": {"data": {"statuses": [{"filled": {"oid": 12345}}]}}}

        try:
            # Note: exchange methods in SDK are typically synchronous initially 
            # and may require running in an executor if strict asyncio is needed.
            # Using execute() method typically supported by HL python SDK
            
            if not self.exchange:
                log.error("Exchange client not initialized")
                return None
                
            # This implements the Post-Only order type
            order_result = self.exchange.order(
                coin=coin,
                is_buy=is_buy,
                sz=float(formatted_sz), # The SDK usually takes float and rounds internally but doing it here guarantees correctness
                limit_px=float(formatted_px),
                order_type={"limit": {"tif": "Alo"}} # Alo = Add Liquidity Only (Post-Only)
            )

            # Check if order was successful
            status = order_result.get("status")
            if status == "ok":
                log.info("Order executed successfully", result=order_result["response"]["data"])
                
                # Try to extract the oid to track it
                try:
                    statuses = order_result["response"]["data"]["statuses"]
                    if statuses and "resting" in statuses[0]:
                        oid = statuses[0]["resting"]["oid"]
                        # In a fully wired setup, the TTL tracker would be called here
                        # self.ttl_tracker.track_order(oid)
                except Exception as e:
                    log.error("Failed to parse OID from resting order", error=str(e))
                
                risk_manager.record_order_result(True)
                return order_result
            else:
                log.error("Order execution failed", response=order_result)
                risk_manager.record_order_result(False)
                return None
                
        except Exception as e:
            log.error("Exception during order execution", error=str(e))
            risk_manager.record_order_result(False)
            return None

    async def close_position(self, coin: str, size: float, is_long: bool) -> Optional[Dict[str, Any]]:
        """
        Sends a market order to close an open position.
        is_long=True  → we are long, so we SELL to close.
        is_long=False → we are short, so we BUY to close.
        """
        mode = risk_manager.state.config.get("execution_mode", "dryrun")
        close_side = not is_long  # sell to close long, buy to close short
        abs_sz = abs(size)

        log.info(
            f"[{mode.upper()}] Closing position (market)",
            coin=coin,
            side="BUY" if close_side else "SELL",
            sz=abs_sz
        )

        if mode == "dryrun":
            risk_manager.record_order_result(True)
            return {"status": "ok", "dryrun": True}

        if not self.exchange:
            log.error("Exchange client not initialized for close_position")
            return None

        try:
            rounded_sz_str = self.rounding.round_size(coin, abs_sz)
            rounded_sz = float(rounded_sz_str)
            if rounded_sz <= 0:
                log.error("Rounded close size is 0", original_sz=abs_sz)
                return None

            # Market order: use a very aggressive limit price (far outside book)
            # Hyperliquid SDK wraps market orders via aggressive IOC limits
            order_result = self.exchange.market_close(coin)
            risk_manager.record_order_result(True)
            return order_result
        except Exception as e:
            log.error("Exception closing position", error=str(e))
            risk_manager.record_order_result(False)
            return None
