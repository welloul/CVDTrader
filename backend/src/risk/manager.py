from typing import Dict, Any
from src.core.logger import log
from src.core.state import state, GlobalState

class RiskManager:
    """Manages pre-trade risk constraints and circuit breakers."""
    
    def __init__(self, global_state: GlobalState):
        self.state = global_state
        self.consecutive_failures = 0
        self.circuit_breaker_active = False

    def check_pre_trade(self, coin: str, sz: float, limit_px: float) -> bool:
        """Evaluates whether an order passes risk checks."""
        
        if self.circuit_breaker_active:
            log.warn("Pre-trade check failed: Circuit breaker is active", coin=coin)
            return False

        if not self.state.is_running:
            log.info("Pre-trade check failed: Bot is stopped", coin=coin)
            return False

        # 1. Check max leverage limit
        if coin in self.state.positions:
            pos = self.state.positions[coin]
            max_leverage = self.state.config.get("max_leverage", 5)
            if pos.leverage > max_leverage:
                log.warn(f"Pre-trade check failed: Leverage {pos.leverage}x exceeds max {max_leverage}x", coin=coin)
                return False

        # 2. Check max position size
        current_sz = self.state.positions[coin].size if coin in self.state.positions else 0.0
        new_total_sz = current_sz + sz 
        notional_value = new_total_sz * limit_px
        
        max_position_size = self.state.config.get("max_position_size_usd", 1000)
        if notional_value > max_position_size * 1.01:  # 1% tolerance for rounding
            log.warn(f"Pre-trade check failed: Notional {notional_value} exceeds max {max_position_size}", coin=coin)
            return False

        # 3. Global account drawdown
        # Placeholder for simplified drawdown logic based on unrealized pnl
        total_unrealized_pnl = sum([p.unrealized_pnl for p in self.state.positions.values()])
        max_drawdown = self.state.config.get("max_drawdown_pct", 5.0)
        
        wallet = self.state.wallet_balance
        if wallet > 0:
            drawdown_pct = (-total_unrealized_pnl / wallet) * 100
            if total_unrealized_pnl < 0 and drawdown_pct > max_drawdown:
                log.warn(f"Pre-trade check failed: Global drawdown {drawdown_pct:.2f}% exceeds max {max_drawdown}%")
                return False

        return True

    def check_latency(self, latency_ms: float):
        """Monitors system latency and triggers circuit breaker if too high."""
        max_latency = self.state.config.get("max_latency_ms", 5000)
        if latency_ms > max_latency and self.state.is_running:
            log.error("High latency detected, activating circuit breaker", latency_ms=latency_ms, max_allowed=max_latency)
            self._activate_circuit_breaker()

    def record_order_result(self, success: bool):
        """Tracks consecutive order failures."""
        if success:
            self.consecutive_failures = 0
            if self.circuit_breaker_active:
                log.info("Order succeeded, resetting circuit breaker")
                self.circuit_breaker_active = False
        else:
            self.consecutive_failures += 1
            if self.consecutive_failures >= 3:
                log.error("Too many consecutive order failures, activating circuit breaker", failures=self.consecutive_failures)
                self._activate_circuit_breaker()

    def _activate_circuit_breaker(self):
        self.circuit_breaker_active = True
        self.state.is_running = False
        log.critical("CIRCUIT BREAKER ACTIVATED: Bot has been stopped.")

    def reset_circuit_breaker(self):
        """Manually reset the circuit breaker to allow trading."""
        self.circuit_breaker_active = False
        self.consecutive_failures = 0
        self.state.is_running = True
        log.info("Circuit breaker manually reset - bot is now running")

risk_manager = RiskManager(state)
