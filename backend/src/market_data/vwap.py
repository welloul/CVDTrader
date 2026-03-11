import datetime
from src.core.logger import log

class DailyVWAPTracker:
    """
    Computes expanding Daily Volume-Weighted Average Price (VWAP).
    Resets at 00:00 UTC.
    """
    
    def __init__(self):
        self.cumulative_pv = 0.0  # Sum of (Price * Volume)
        self.cumulative_vol = 0.0 # Sum of Volume
        self.current_vwap = 0.0
        
        # Track the active trading day
        self.current_day: int = -1

    def _check_rollover(self, tsMs: float):
        """Checks if the timestamp has crossed into a new UTC day."""
        dt = datetime.datetime.utcfromtimestamp(tsMs / 1000.0)
        
        if self.current_day == -1:
            self.current_day = dt.day
            return
            
        if dt.day != self.current_day:
            log.info("Daily VWAP Rollover", prev_vwap=self.current_vwap, new_day=dt.isoformat())
            # Reset accumulators for the new day
            self.cumulative_pv = 0.0
            self.cumulative_vol = 0.0
            self.current_day = dt.day

    def process_trade(self, tsMs: float, price: float, volume: float) -> float:
        """
        Processes a raw tick and updates the VWAP.
        Uses execution price as typical price since we process tick-by-tick.
        """
        self._check_rollover(tsMs)
        
        self.cumulative_pv += (price * volume)
        self.cumulative_vol += volume
        
        if self.cumulative_vol > 0:
            self.current_vwap = self.cumulative_pv / self.cumulative_vol
            
        return self.current_vwap
