import asyncio
from typing import Dict, Any, Optional
from hyperliquid.exchange import Exchange
from hyperliquid.utils import signing
from src.core.logger import log
from src.core.rounding import RoundingUtil
from src.risk.manager import risk_manager

# Order timeout in seconds (cancel if not filled)
ORDER_TIMEOUT_SECONDS = 10

class ExecutionGateway:
    """Handles execution logic on Hyperliquid."""
    
    def __init__(self, exchange_client: Exchange, rounding_util: RoundingUtil, ttl_tracker=None):
        self.exchange = exchange_client
        self.rounding = rounding_util
        self.ttl_tracker = ttl_tracker

    async def execute_limit_order(self, coin: str, is_buy: bool, sz: float, limit_px: float,
                                  stop_loss: float = 0, take_profit: float = 0) -> Optional[Dict[str, Any]]:
        """
        Executes a Post-Only Limit Order with optional TP/SL.
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

            # Set isolated margin before placing order (always use isolated)
            leverage = int(risk_manager.state.config.get("max_leverage", 5))
            try:
                # Set to isolated margin with specified leverage
                self.exchange.update_isolated_margin(coin, True)
                self.exchange.update_leverage(coin, leverage)
                log.info("Set isolated margin and leverage", coin=coin, leverage=leverage)
            except Exception as e:
                log.warning("Failed to set isolated margin, continuing with order", error=str(e))

            # This implements the Post-Only order type
            order_result = self.exchange.order(
                name=coin,
                is_buy=is_buy,
                sz=float(formatted_sz), # The SDK usually takes float and rounds internally but doing it here guarantees correctness
                limit_px=float(formatted_px),
                order_type={"limit": {"tif": "Alo"}} # Alo = Add Liquidity Only (Post-Only)
            )

            # Check if order was successful
            status = order_result.get("status")
            if status == "ok":
                log.info("Order executed successfully", result=order_result["response"]["data"])
                
                # Track the order in state as active
                try:
                    statuses = order_result["response"]["data"]["statuses"]
                    if statuses:
                        if "filled" in statuses[0]:
                            # Order was immediately filled
                            oid = statuses[0]["filled"]["oid"]
                        elif "resting" in statuses[0]:
                            # Order is resting on book
                            oid = statuses[0]["resting"]["oid"]
                            log.info("Order resting on book, will cancel if not filled in 2s", oid=oid)
                        
                        # Add to active orders in state via risk_manager
                        if oid:
                            # Access state through risk_manager
                            state = risk_manager.state
                            state.active_orders[oid] = type('ActiveOrder', (), {
                                'coin': coin,
                                'is_buy': is_buy,
                                'sz': rounded_sz,
                                'limit_px': rounded_px
                            })()
                            
                            # Track order in TTL tracker for stale order cancellation
                            if self.ttl_tracker:
                                self.ttl_tracker.track_order(oid, ttl_seconds=120)  # 2 min TTL
                except Exception as e:
                    log.error("Failed to track order in active_orders", error=str(e))
                
                # Send TP/SL orders immediately after entry order
                if stop_loss > 0 or take_profit > 0:
                    await self._send_tpsl_orders(coin, is_buy, rounded_sz, stop_loss, take_profit)
                
                # Wait and cancel if not filled
                if oid:
                    await self._wait_and_cancel(coin, oid)
                
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

    async def _send_tpsl_orders(self, coin: str, is_buy: bool, sz: float, 
                                stop_loss: float, take_profit: float) -> None:
        """
        Send TP and SL trigger orders to Hyperliquid.
        
        For LONG: TP is above entry, SL is below entry
        For SHORT: TP is below entry, SL is above entry
        """
        try:
            # For LONG: close by selling (is_buy=False for close)
            # For SHORT: close by buying (is_buy=True for close)
            close_is_buy = not is_buy  # Opposite of entry
            
            # Send Take Profit order (use market when triggered)
            if take_profit > 0:
                tp_trigger_px = self.rounding.round_price(coin, take_profit)
                
                # Use trigger order type - isMarket=True means market order when triggered
                tp_order_type = {
                    "trigger": {
                        "triggerPx": float(tp_trigger_px),
                        "isMarket": True,  # Use market order when triggered
                        "tpsl": "tp"
                    }
                }
                
                tp_result = self.exchange.order(
                    name=coin,
                    is_buy=close_is_buy,
                    sz=sz,
                    limit_px=float(tp_trigger_px),
                    order_type=tp_order_type,
                    reduce_only=True  # This is a closing order
                )
                log.info("TP order sent", coin=coin, tp_price=take_profit, result=tp_result)
            
            # Send Stop Loss order (use market when triggered)
            if stop_loss > 0:
                sl_trigger_px = self.rounding.round_price(coin, stop_loss)
                
                sl_order_type = {
                    "trigger": {
                        "triggerPx": float(sl_trigger_px),
                        "isMarket": True,  # Use market order when triggered
                        "tpsl": "sl"
                    }
                }
                
                sl_result = self.exchange.order(
                    name=coin,
                    is_buy=close_is_buy,
                    sz=sz,
                    limit_px=float(sl_trigger_px),
                    order_type=sl_order_type,
                    reduce_only=True  # This is a closing order
                )
                log.info("SL order sent", coin=coin, sl_price=stop_loss, result=sl_result)
                
        except Exception as e:
            log.error("Failed to send TP/SL orders", error=str(e), coin=coin)

    async def _wait_and_cancel(self, coin: str, oid: int) -> None:
        """
        Wait for ORDER_TIMEOUT_SECONDS and cancel the order if not filled.
        This prevents stale limit orders from sitting on the order book.
        """
        log.info("Waiting to check if order fills...", coin=coin, oid=oid, timeout=ORDER_TIMEOUT_SECONDS)
        await asyncio.sleep(ORDER_TIMEOUT_SECONDS)
        
        if not self.exchange:
            log.warning("Exchange not available for cancel check")
            return
            
        try:
            # Check if order is still open using the API
            # Get open orders for this coin using info()
            user = self.exchange.info.user()
            
            # Handle different response formats
            open_orders = []
            if isinstance(user, dict):
                # Try various possible keys
                open_orders = user.get("openOrders", [])
                if not open_orders:
                    # Check if orders are in a different structure
                    pending = user.get("pending", [])
                    if pending:
                        open_orders = pending
            elif isinstance(user, list):
                open_orders = user
            
            log.debug("Open orders check", coin=coin, oid=oid, open_count=len(open_orders))
            
            order_still_open = False
            for order in open_orders:
                # Handle both dict and other formats
                order_oid = None
                if isinstance(order, dict):
                    order_oid = order.get("oid") or order.get("id")
                
                # Convert to int for comparison if needed
                if order_oid:
                    try:
                        if int(order_oid) == int(oid):
                            order_still_open = True
                            break
                    except (ValueError, TypeError):
                        pass
            
            if order_still_open:
                log.info("Order not filled after timeout, cancelling", coin=coin, oid=oid)
                try:
                    cancel_result = self.exchange.cancel(coin, oid)
                    log.info("Cancel result", coin=coin, oid=oid, result=cancel_result)
                except Exception as cancel_err:
                    log.error("Cancel call failed", error=str(cancel_err), coin=coin, oid=oid)
            else:
                log.info("Order was filled or not found, no need to cancel", coin=coin, oid=oid)
                
        except Exception as e:
            log.error("Error in wait_and_cancel", error=str(e), coin=coin, oid=oid)

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
