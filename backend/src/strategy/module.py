import asyncio
import os
import time
import uuid
import datetime
from typing import Dict, Any, Optional, List
from src.core.logger import log
from src.core.state import GlobalState, Position, ActiveOrder, ClosedTrade
from src.market_data.handler import MarketDataHandler
from src.market_data.candles import Candle
from src.execution.gateway import ExecutionGateway
from src.risk.manager import RiskManager

LOOKBACK = 20  # candles to consider for swing high/low and CVD percentile
CVD_EXHAUSTION_RATIO = 0.70  # CVD must drop to 70% of previous (30% lower)
CVD_ABSORPTION_PCTILE = 0.90  # Top 10% of recent CVD magnitudes
# VWAP_TOLERANCE = 0.005  # ±0.5% tolerance around VWAP (DISABLED 2026-03-10 for performance comparison)
VWAP_FILTER_ENABLED = False  # Set to False to disable VWAP filter (disabled 2026-03-10T15:00 UTC for A/B testing)

# Breakeven fee adjustment - ensures trades cover their own costs
FIXED_FEE_RATE = 0.0003  # 0.03% fee rate (Hyperliquid maker/taker approximation)


class StrategyModule:
    """Connects indicators, risk, and execution via event-driven design.
    
    Implements the Delta-POC Reversal strategy with two setups:
        A) Exhaustion – price makes new swing high/low but CVD conviction drops
        B) Absorption – price makes new swing high/low but range shrinks while CVD is extreme

    Exit Engine (CVD-based trailing stop):
        1. CVD declining (same sign, weakening magnitude) → tighten SL to prev candle POC
        2. CVD flips (sign reversal vs. entry direction)   → tighten SL to current candle POC
        3. Two consecutive CVD flip candles                → close immediately at market
        Also: SL or TP hit on any tick → close immediately.
    """

    def __init__(self, state: GlobalState, execution: Optional[ExecutionGateway], risk: RiskManager, ttl_tracker: Optional[Any] = None):
        self.state = state
        self.execution = execution
        self.risk = risk
        self.ttl_tracker = ttl_tracker

        # Per-coin reference to the CandleBuilder closed_candles list
        # Populated from the MarketDataHandler event
        self._candle_history: Dict[str, List[Candle]] = {}

        # Exit engine tracking: consecutive CVD-flip candles per coin
        self._cvd_flip_streak: Dict[str, int] = {}

    def calculate_breakeven(self, entry_price: float, size: float, is_buy: bool) -> float:
        """Calculates fee-adjusted breakeven price.
        
        Formula: EntryPrice * (1 + 0.0003) for LONG
                 EntryPrice * (1 - 0.0003) for SHORT
        
        This ensures that a "breakeven" trade actually covers the 0.03% fee.
        """
        if entry_price <= 0:
            return entry_price
        fee_multiplier = FIXED_FEE_RATE
        if is_buy:
            # LONG: breakeven is above entry (need price to rise to cover fee)
            return entry_price * (1 + fee_multiplier)
        else:
            # SHORT: breakeven is below entry (need price to fall to cover fee)
            return entry_price * (1 - fee_multiplier)

    # ------------------------------------------------------------------
    # Event entry point
    # ------------------------------------------------------------------
    async def on_market_data(self, event: Dict[str, Any]):
        """Event listener for every trade tick dispatched by MarketDataHandler."""

        latency = event.get("latency_ms", 0)
        self.risk.check_latency(latency)

        coin = event["coin"]

        # Initialise per-coin market_data bucket
        if coin not in self.state.market_data:
            self.state.market_data[coin] = {
                "candles": [],
                "cvd": [],
                "price": 0.0,
                "indicators": {}
            }

        # Live price + indicators (always updated regardless of is_running)
        self.state.market_data[coin]["price"] = event["price"]
        self.state.market_data[coin]["indicators"] = event.get("indicators", {})

        # Update simulated PnL on every tick (dryrun)
        self.update_simulated_pnl(coin, event["price"])

        # --- Tick-level SL / TP check ---
        await self._check_sl_tp(coin, event["price"])

        closed_1m: Optional[Candle] = event.get("closed_candle_1m")
        vwap = event.get("vwap", 0.0)

        # ---- Candle history accumulation (always, even when stopped) ----
        if closed_1m:
            history = self.state.market_data[coin]["candles"]
            if not any(c["time"] == closed_1m.start_time for c in history):
                history.append({
                    "time": closed_1m.start_time,
                    "open": closed_1m.open,
                    "high": closed_1m.high,
                    "low": closed_1m.low,
                    "close": closed_1m.close,
                    "cvd": closed_1m.cvd,
                    "poc": closed_1m.poc
                })
                if len(history) > 100:
                    history.pop(0)

                log.info(
                    f"1m Candle Closed [{coin}]",
                    close=closed_1m.close,
                    cvd=round(closed_1m.cvd, 4),
                    poc=closed_1m.poc,
                    vwap=round(vwap, 2)
                )

            # Keep a reference to the raw Candle objects for strategy logic
            if coin not in self._candle_history:
                self._candle_history[coin] = []
            ch = self._candle_history[coin]
            if not ch or ch[-1].start_time != closed_1m.start_time:
                ch.append(closed_1m)
                if len(ch) > LOOKBACK + 5:
                    ch.pop(0)

        # ---- Guard: strategy only runs when bot is started ----
        if not self.state.is_running:
            return

        if not closed_1m:
            return

        # ---- Exit management: runs on each candle close when in a position ----
        if coin in self.state.positions:
            ch = self._candle_history.get(coin, [])
            if len(ch) >= 2:
                await self._manage_position_exit(coin, ch[-1], ch[-2])
            return  # don't evaluate new entries while holding

        # ---- Guard: skip if pending order for this coin ----
        if any(o.coin == coin for o in self.state.active_orders.values()):
            return

        # ---- Evaluate Delta-POC Reversal ----
        await self._evaluate_signal(coin, closed_1m, vwap)

    # ------------------------------------------------------------------
    # Core strategy: multi-candle Delta-POC evaluation
    # ------------------------------------------------------------------
    async def _evaluate_signal(self, coin: str, candle: Candle, vwap: float):
        ch = self._candle_history.get(coin, [])
        if len(ch) < 3:
            log.info(f"[DEBUG] {coin}: Need more candles ({len(ch)}/3)")
            return  # Need at least prev + current + some history

        prev = ch[-2]
        curr = ch[-1]

        if not curr.poc:
            log.info(f"[DEBUG] {coin}: No POC yet")
            return

        # --- Swing detection over lookback ---
        lookback = ch[-(LOOKBACK + 1):-1] if len(ch) > LOOKBACK else ch[:-1]
        highest_high = max(c.high for c in lookback) if lookback else curr.high
        lowest_low = min(c.low for c in lookback) if lookback else curr.low

        is_new_high = curr.high >= highest_high
        is_new_low = curr.low <= lowest_low

        log.info(f"[DEBUG] {coin}: highs={curr.high}/{highest_high} new_high={is_new_high}, lows={curr.low}/{lowest_low} new_low={is_new_low}")

        if not is_new_high and not is_new_low:
            return  # No swing extreme — no setup

        # --- Check setup conditions ---
        abs_cvd_curr = abs(curr.cvd)
        abs_cvd_prev = abs(prev.cvd)
        curr_range = curr.high - curr.low
        prev_range = prev.high - prev.low

        # Condition A: Exhaustion
        #   Price makes new extreme but delta conviction drops ≥30%
        is_exhaustion = (
            abs_cvd_prev > 0 and
            abs_cvd_curr < abs_cvd_prev * CVD_EXHAUSTION_RATIO
        )

        # Condition B: Absorption
        #   Price makes new extreme, range contracts, but CVD is in top 10%
        cvd_magnitudes = sorted([abs(c.cvd) for c in lookback]) if lookback else []
        threshold_90 = cvd_magnitudes[int(len(cvd_magnitudes) * CVD_ABSORPTION_PCTILE)] if len(cvd_magnitudes) > 5 else float('inf')

        is_absorption = (
            curr_range < prev_range and  # range contraction
            abs_cvd_curr >= threshold_90   # CVD in top 10%
        )

        if not is_exhaustion and not is_absorption:
            return

        setup_type = "Exhaustion" if is_exhaustion else "Absorption"

        # --- Flip validation ---
        midpoint = (curr.high + curr.low) / 2.0
        is_upper_poc = curr.profile.is_upper_half(curr.poc, curr.high, curr.low)

        # Bear reversal: close below midpoint, POC in upper half
        is_bear_reversal = curr.close < midpoint and is_upper_poc
        # Bull reversal: close above midpoint, POC in lower half
        is_bull_reversal = curr.close > midpoint and not is_upper_poc

        # --- VWAP filter with ±0.5% tolerance (automatic mean reversion) ---
        # VWAP_FILTER_ENABLED = False (DISABLED 2026-03-10T15:00 UTC for A/B testing)
        if VWAP_FILTER_ENABLED:
            # Market automatically dictates direction based on price position relative to VWAP
            vwap_upper = vwap * (1 + VWAP_TOLERANCE)
            vwap_lower = vwap * (1 - VWAP_TOLERANCE)
            
            # Automatic VWAP-based filtering (mean reversion):
            # - Price > VWAP + 0.5% → Allow SHORT only (too high, expect pullback)
            # - Price < VWAP - 0.5% → Allow LONG only (too low, expect bounce)
            # - Price within ±0.5% of VWAP → Allow BOTH directions
            
            is_significantly_above_vwap = curr.close > vwap_upper
            is_significantly_below_vwap = curr.close < vwap_lower
            is_in_middle_zone = not is_significantly_above_vwap and not is_significantly_below_vwap
            
            # Allow SHORT when price is above VWAP (mean reversion: sell high)
            allow_short = is_significantly_above_vwap or is_in_middle_zone
            # Allow LONG when price is below VWAP (mean reversion: buy low)
            allow_long = is_significantly_below_vwap or is_in_middle_zone
        else:
            # VWAP filter disabled - allow all directions
            allow_short = True
            allow_long = True

        entry_price = curr.poc

        # Calculate position size for profit checking
        max_position_usd = float(os.getenv('MAX_POSITION_SIZE_USD', '1000'))
        position_size = max_position_usd / entry_price  # Approximate size in coins

        # Minimum profit threshold ($0.40)
        min_profit_usd = 0.40

        if is_bear_reversal and allow_short and is_new_high:
            # Wick-based SL: SL = Entry + (wick * 2), TP = Entry - (wick * 2 * 1.5)
            wick = curr.high - entry_price
            stop_loss = entry_price + (wick * 2)  # 2x wick size above entry
            take_profit = entry_price - (wick * 2 * 1.5)  # 1.5x R ratio
            
            # Ensure minimum $0.40 profit
            potential_profit = (entry_price - take_profit) * position_size
            if potential_profit < min_profit_usd:
                # Adjust TP to guarantee $0.40 profit
                min_tp_distance = min_profit_usd / position_size
                take_profit = entry_price - min_tp_distance
            log.info(
                f"📉 SIGNAL: SHORT [{coin}] ({setup_type})",
                entry=entry_price, sl=stop_loss, tp=round(take_profit, 2),
                cvd=round(curr.cvd, 4), poc=entry_price, vwap=round(vwap, 2)
            )
            self.state.add_log(
                "WARN",
                f"📉 SHORT Signal [{coin}] @ ${entry_price:,.2f} ({setup_type}) SL=${stop_loss:,.2f} TP=${take_profit:,.2f}"
            )
            await self._try_enter_position(coin, is_buy=False, price=entry_price,
                                           stop_loss=stop_loss, take_profit=take_profit,
                                           entry_reason=setup_type)

        elif is_bull_reversal and allow_long and is_new_low:
            # Wick-based SL: SL = Entry - (wick * 2), TP = Entry + (wick * 2 * 1.5)
            wick = entry_price - curr.low
            stop_loss = entry_price - (wick * 2)  # 2x wick size below entry
            take_profit = entry_price + (wick * 2 * 1.5)  # 1.5x R ratio
            
            # Ensure minimum $0.40 profit
            potential_profit = (take_profit - entry_price) * position_size
            if potential_profit < min_profit_usd:
                # Adjust TP to guarantee $0.40 profit
                min_tp_distance = min_profit_usd / position_size
                take_profit = entry_price + min_tp_distance
            log.info(
                f"📈 SIGNAL: LONG [{coin}] ({setup_type})",
                entry=entry_price, sl=stop_loss, tp=round(take_profit, 2),
                cvd=round(curr.cvd, 4), poc=entry_price, vwap=round(vwap, 2)
            )
            self.state.add_log(
                "WARN",
                f"📈 LONG Signal [{coin}] @ ${entry_price:,.2f} ({setup_type}) SL=${stop_loss:,.2f} TP=${take_profit:,.2f}"
            )
            await self._try_enter_position(coin, is_buy=True, price=entry_price,
                                           stop_loss=stop_loss, take_profit=take_profit,
                                           entry_reason=setup_type)

    # ------------------------------------------------------------------
    # Position entry
    # ------------------------------------------------------------------
    async def _try_enter_position(self, coin: str, is_buy: bool, price: float,
                                   stop_loss: float = 0, take_profit: float = 0,
                                   entry_reason: str = ""):
        """Attempts to enter a position if one doesn't exist."""

        # Check if there's already a position for this coin
        if coin in self.state.positions:
            current_pos = self.state.positions[coin]
            # Calculate current position value
            current_value = abs(current_pos.size) * current_pos.entry_price
            max_usd = self.state.config.get("max_position_size_usd", 1000)
            
            if current_value >= max_usd * 0.9:  # 90% of max = already at limit
                log.info(f"Position size limit reached for {coin}, skipping", 
                        current_value=round(current_value, 2), max=max_usd)
                return
        
        # Check if there's an active order for this coin
        for order in self.state.active_orders.values():
            if order.coin == coin:
                log.info(f"Active order exists for {coin}, skipping")
                return

        max_usd = self.state.config.get("max_position_size_usd", 1000)
        target_sz = max_usd / price

        # Offset limit price for maker fill
        # For LONG: buy slightly below market (0.999) so it sits on bid
        # For SHORT: sell slightly above market (1.001) so it sits on ask
        # This ensures post-only orders are maker orders
        limit_px = price * 0.999 if is_buy else price * 1.001

        # Calculate fee-adjusted breakeven price
        breakeven_px = self.calculate_breakeven(price, target_sz, is_buy)

        side_str = "BUY" if is_buy else "SELL"
        log.info(f"Placing {side_str} order", coin=coin, sz=round(target_sz, 6), limit_px=round(limit_px, 2), breakeven=round(breakeven_px, 4))

        mode = self.state.config.get("execution_mode", "dryrun")

        # Reset CVD flip streak for this coin on new entry
        self._cvd_flip_streak[coin] = 0

        if mode == "dryrun":
            # Simulate a filled position directly in state
            self._simulate_fill(coin, is_buy, target_sz, price, stop_loss, take_profit, breakeven_px, entry_reason)
            return

        if self.execution:
            result = await self.execution.execute_limit_order(
                coin=coin,
                is_buy=is_buy,
                sz=target_sz,
                limit_px=limit_px,
                stop_loss=stop_loss,
                take_profit=take_profit
            )
            
            # In live mode, track the position immediately after order is placed
            # The position will be managed by exit logic based on SL/TP
            if result and result.get("status") == "ok":
                signed_sz = target_sz if is_buy else -target_sz
                side_str = "LONG" if is_buy else "SHORT"
                self.state.positions[coin] = Position(
                    coin=coin,
                    size=signed_sz,
                    entry_price=price,
                    leverage=self.state.config.get("max_leverage", 5),
                    unrealized_pnl=0.0,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    breakeven=breakeven_px,
                    side=side_str,
                    opened_at=datetime.datetime.utcnow().isoformat() + "Z",
                    entry_reason=entry_reason,
                    tp_50_hit=False,
                    trailing_sl=0.0,
                    original_tp=take_profit
                )
                self.state.add_log(
                    "INFO",
                    f"✅ ORDER PLACED {side_str} {coin} "
                    f"sz={abs(signed_sz):.6f} @ ${price:,.2f} | SL=${stop_loss:,.2f} TP=${take_profit:,.2f}"
                )
                log.info("Position tracked in state for exit management", 
                        coin=coin, side=side_str, sl=stop_loss, tp=take_profit)

    # ------------------------------------------------------------------
    # Dryrun simulation
    # ------------------------------------------------------------------
    def _simulate_fill(self, coin: str, is_buy: bool, sz: float, fill_px: float,
                        stop_loss: float = 0, take_profit: float = 0, breakeven: float = 0.0,
                        entry_reason: str = ""):
        """Creates a simulated position in GlobalState for dryrun mode."""
        signed_sz = sz if is_buy else -sz
        side_str = "LONG" if is_buy else "SHORT"
        
        # Use calculated breakeven or fallback to entry price
        breakeven_px = breakeven if breakeven > 0 else fill_px
        
        self.state.positions[coin] = Position(
            coin=coin,
            size=signed_sz,
            entry_price=fill_px,
            leverage=self.state.config.get("max_leverage", 5),
            unrealized_pnl=0.0,
            stop_loss=stop_loss,
            take_profit=take_profit,
            breakeven=breakeven_px,
            side=side_str,
            opened_at=datetime.datetime.utcnow().isoformat() + "Z",
            tp_50_hit=False,
            trailing_sl=0.0,
            original_tp=take_profit,
            entry_reason=entry_reason,
            sl_modifications=[]
        )
        self.state.add_log(
            "INFO",
            f"✅ FILLED (dryrun) {side_str} {coin} "
            f"sz={abs(signed_sz):.6f} @ ${fill_px:,.2f} | SL=${stop_loss:,.2f} TP=${take_profit:,.2f} BE=${breakeven_px:,.2f}"
        )
        log.info(
            f"Dryrun fill simulated",
            coin=coin, side=side_str,
            sz=round(abs(signed_sz), 6), fill_px=fill_px, breakeven=breakeven_px
        )

    # ------------------------------------------------------------------
    # Dryrun PnL updater (called from market data ticks)
    # ------------------------------------------------------------------
    def update_simulated_pnl(self, coin: str, current_price: float):
        """Updates unrealised PnL for simulated dryrun positions."""
        if coin not in self.state.positions:
            return
        pos = self.state.positions[coin]
        if pos.size > 0:  # long
            pos.unrealized_pnl = (current_price - pos.entry_price) * abs(pos.size)
        else:  # short
            pos.unrealized_pnl = (pos.entry_price - current_price) * abs(pos.size)

    # ------------------------------------------------------------------
    # Tick-level SL / TP check
    # ------------------------------------------------------------------
    async def _check_sl_tp(self, coin: str, price: float):
        """Closes position immediately if current price crosses SL or TP."""
        if coin not in self.state.positions:
            return
        pos = self.state.positions[coin]
        if pos.stop_loss == 0 and pos.take_profit == 0:
            return

        is_long = pos.side == "LONG"

        # Check if trailing SL is hit (for remaining 50% after partial TP)
        hit_trailing_sl = pos.tp_50_hit and pos.trailing_sl > 0 and (
            (is_long and price <= pos.trailing_sl) or
            (not is_long and price >= pos.trailing_sl)
        )

        hit_sl = (is_long and price <= pos.stop_loss) or (not is_long and price >= pos.stop_loss)
        hit_tp = pos.take_profit > 0 and not pos.tp_50_hit and (
            (is_long and price >= pos.take_profit) or
            (not is_long and price <= pos.take_profit)
        )

        if hit_trailing_sl:
            # Close remaining 50% when trailing SL is hit
            await self._close_position(coin, f"Trailing SL hit @ {price:.4f}", price)
        elif hit_sl:
            await self._close_position(coin, f"SL hit @ {price:.4f}", price)
        elif hit_tp:
            # Partial TP: close 50% at TP, set trailing SL for remaining 50%
            await self._close_partial_at_tp(coin, price)

    # ------------------------------------------------------------------
    # Partial TP handler - close 50% at TP, set trailing SL for remaining 50%
    # ------------------------------------------------------------------
    async def _close_partial_at_tp(self, coin: str, close_price: float):
        """Closes 50% of position at TP and sets trailing SL for remaining 50%."""
        if coin not in self.state.positions:
            return
        pos = self.state.positions[coin]
        
        # Calculate 50% size
        half_size = abs(pos.size) / 2
        is_long = pos.side == "LONG"
        
        # Calculate PnL for 50%
        if is_long:
            pnl_50 = (close_price - pos.entry_price) * half_size
        else:
            pnl_50 = (pos.entry_price - close_price) * half_size
        
        log.info(f"Partial TP [{coin}]: closing 50% @ {close_price:.4f}", 
                 pnl=round(pnl_50, 4), half_size=half_size)
        self.state.add_log(
            "INFO",
            f"🎯 PARTIAL TP {pos.side} [{coin}] @ ${close_price:,.4f} "
            f"Closed 50%: sz={half_size:.6f} PnL=${pnl_50:+.4f}"
        )
        
        # Record closed trade for the 50%
        closed_at = datetime.datetime.utcnow().isoformat() + "Z"
        trade = ClosedTrade(
            id=str(uuid.uuid4()),
            coin=coin,
            side=pos.side,
            size=half_size,
            entry_price=pos.entry_price,
            exit_price=close_price,
            pnl=round(pnl_50, 6),
            reason="50% TP hit",
            opened_at=pos.opened_at or closed_at,
            closed_at=closed_at
        )
        self.state.closed_trades.append(trade)
        self.state._save_trades()
        
        # Update remaining position (50%)
        if is_long:
            pos.size = half_size
        else:
            pos.size = -half_size
        
        # Update unrealized PnL for remaining 50%
        if is_long:
            pos.unrealized_pnl = (close_price - pos.entry_price) * half_size
        else:
            pos.unrealized_pnl = (pos.entry_price - close_price) * half_size
        
        # Set trailing SL at TP price for remaining 50%
        pos.tp_50_hit = True
        pos.trailing_sl = pos.take_profit  # Set trailing SL to original TP
        
        # Clear the take_profit since we've already taken partial profit
        pos.take_profit = 0
        
        self.state.add_log(
            "INFO",
            f"📍 Trailing SL set @ ${pos.trailing_sl:,.4f} for remaining 50%"
        )

    # ------------------------------------------------------------------
    # CVD-based trailing stop management (called on each candle close)
    # ------------------------------------------------------------------
    async def _manage_position_exit(self, coin: str, curr: Candle, prev: Candle):
        """
        Adjusts stop-loss dynamically based on CVD behaviour:

        Rule 1 — CVD declining (same sign, magnitude dropping):
            Tighten SL to previous candle's POC.

        Rule 2 — CVD flips (sign reversal vs. entry direction):
            Tighten SL to current candle's POC.
            Start tracking flip streak.

        For partial TP positions (50% closed at TP):
            Update trailing_sl to previous POC when price moves favorably.
        """
        if coin not in self.state.positions:
            return
        pos = self.state.positions[coin]
        if not curr.poc or not prev.poc:
            return

        is_long = pos.side == "LONG"

        # CVD signs for the two candles
        curr_sign = 1 if curr.cvd > 0 else -1
        prev_sign = 1 if prev.cvd > 0 else -1

        # The "favourable" CVD sign for this position
        # Long wants positive CVD (buyers in control), Short wants negative CVD
        fav_sign = 1 if is_long else -1

        cvd_flipped = curr_sign != fav_sign  # current candle CVD is working against us

        if cvd_flipped:
            self._cvd_flip_streak[coin] = self._cvd_flip_streak.get(coin, 0) + 1
        else:
            self._cvd_flip_streak[coin] = 0  # reset streak when CVD is back in our favour

        # ---- Handle partial TP positions: update trailing_sl to POC when price moves favorably ----
        if pos.tp_50_hit and pos.trailing_sl > 0 and not cvd_flipped and curr.poc:
            # Price is moving favorably, update trailing_sl to current POC
            new_trailing_sl = curr.poc
            old_trailing_sl = pos.trailing_sl
            
            if is_long:
                # For longs, only update if POC is higher (more profit potential)
                if new_trailing_sl > old_trailing_sl:
                    pos.trailing_sl = new_trailing_sl
                    msg = f"Partial TP → trailing SL → curr POC {new_trailing_sl:.4f}"
                    log.info(msg, coin=coin, old_sl=old_trailing_sl, new_sl=new_trailing_sl)
                    self.state.add_log("INFO", f"📍 [{coin}] {msg}")
            else:
                # For shorts, only update if POC is lower (more profit potential)
                if new_trailing_sl < old_trailing_sl:
                    pos.trailing_sl = new_trailing_sl
                    msg = f"Partial TP → trailing SL → curr POC {new_trailing_sl:.4f}"
                    log.info(msg, coin=coin, old_sl=old_trailing_sl, new_sl=new_trailing_sl)
                    self.state.add_log("INFO", f"📍 [{coin}] {msg}")
            # Don't return here - continue to also handle regular SL management

        # ---- Rule 2: one CVD flip → tighten SL to current POC ----
        if cvd_flipped and curr.poc:
            new_sl = curr.poc
            old_sl = pos.stop_loss
            # Only move SL in the profitable direction (don't widen)
            if is_long:
                if new_sl > old_sl:  # higher SL is tighter for a long
                    pos.stop_loss = new_sl
                    msg = f"CVD flip ↗ tightened SL → curr POC {new_sl:.4f}"
                    log.info(msg, coin=coin, old_sl=old_sl, new_sl=new_sl)
                    self.state.add_log("INFO", f"🔒 [{coin}] {msg}")
            else:
                if new_sl < old_sl:  # lower SL is tighter for a short
                    pos.stop_loss = new_sl
                    msg = f"CVD flip ↘ tightened SL → curr POC {new_sl:.4f}"
                    log.info(msg, coin=coin, old_sl=old_sl, new_sl=new_sl)
                    self.state.add_log("INFO", f"🔒 [{coin}] {msg}")
            return

        # ---- Rule 1: CVD declining (same direction, weakening magnitude) ----
        cvd_declining = (curr_sign == fav_sign) and (abs(curr.cvd) < abs(prev.cvd))
        if cvd_declining and prev.poc:
            new_sl = prev.poc
            old_sl = pos.stop_loss
            if is_long:
                if new_sl > old_sl:
                    pos.stop_loss = new_sl
                    msg = f"CVD declining ↘ tightened SL → prev POC {new_sl:.4f}"
                    log.info(msg, coin=coin, old_sl=old_sl, new_sl=new_sl)
                    self.state.add_log("INFO", f"🔒 [{coin}] {msg}")
            else:
                if new_sl < old_sl:
                    pos.stop_loss = new_sl
                    msg = f"CVD declining ↗ tightened SL → prev POC {new_sl:.4f}"
                    log.info(msg, coin=coin, old_sl=old_sl, new_sl=new_sl)
                    self.state.add_log("INFO", f"🔒 [{coin}] {msg}")

    # ------------------------------------------------------------------
    # Position close
    # ------------------------------------------------------------------
    async def _close_position(self, coin: str, reason: str, close_price: float):
        """Closes an open position (dryrun: remove from state; live: market order)."""
        if coin not in self.state.positions:
            return
        pos = self.state.positions[coin]
        pnl = pos.unrealized_pnl
        mode = self.state.config.get("execution_mode", "dryrun")

        log.info(f"Closing position [{coin}]", reason=reason, pnl=round(pnl, 4), price=close_price)
        self.state.add_log(
            "WARN" if pnl < 0 else "INFO",
            f"{'🔴' if pnl < 0 else '🟢'} CLOSE {pos.side} [{coin}] @ ${close_price:,.4f} "
            f"PnL=${pnl:+.4f} | Entry=${pos.entry_price:,.2f} BE=${pos.breakeven:,.2f} | {reason}"
        )

        # Record closed trade in history
        closed_at = datetime.datetime.utcnow().isoformat() + "Z"
        trade = ClosedTrade(
            id=str(uuid.uuid4()),
            coin=coin,
            side=pos.side,
            size=abs(pos.size),
            entry_price=pos.entry_price,
            exit_price=close_price,
            pnl=round(pnl, 6),
            reason=reason,
            opened_at=pos.opened_at or closed_at,
            closed_at=closed_at,
            entry_reason=pos.entry_reason,
            sl_modifications=pos.sl_modifications
        )
        self.state.closed_trades.append(trade)
        self.state._save_trades()

        if mode != "dryrun" and self.execution:
            await self.execution.close_position(coin, pos.size, is_long=(pos.side == "LONG"))

        # Remove position from state
        del self.state.positions[coin]
        # Reset flip tracking
        self._cvd_flip_streak[coin] = 0
