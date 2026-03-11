import time
from typing import Dict, List, Optional
from src.core.logger import log
from src.market_data.profile import VolumeProfileBuilder

class Candle:
    """Represents a single custom aggregated timeframe bar."""
    def __init__(self, timestamp: float, open_px: float, tick_size: float = 1.0):
        self.start_time = timestamp
        self.open = open_px
        self.high = open_px
        self.low = open_px
        self.close = open_px
        self.volume = 0.0
        
        # Track CVD for this specific candle (Delta-POC logic)
        self.cvd = 0.0
        
        # Track the inner volume profile
        self.profile = VolumeProfileBuilder(tick_size)
        self.poc: Optional[float] = None
        
    def add_trade(self, price: float, sz: float, is_buy: bool):
        """Update candle boundaries and volume."""
        self.close = price
        if price > self.high:
            self.high = price
        if price < self.low:
            self.low = price
            
        self.volume += sz
        
        # Intra-candle CVD
        delta = sz if is_buy else -sz
        self.cvd += delta
        
        # Add to the profile to track the POC
        self.profile.add_trade(price, sz)

    def finalize(self):
        """Locks in the POC when the candle finishes rolling."""
        self.poc = self.profile.get_poc()

    @property
    def range(self) -> float:
        return self.high - self.low


class CandleBuilder:
    """
    Aggregates realtime WS trades into OHLCV candles (1m, 15m) for the strategy.
    """
    
    def __init__(self, timeframe_seconds: int = 60, tick_size: float = 1.0, history_len: int = 100):
        self.timeframe = timeframe_seconds
        self.tick_size = tick_size
        
        self.current_candle: Optional[Candle] = None
        self.closed_candles: List[Candle] = []
        self.max_history = history_len

    def _get_bin_timestamp(self, tsMs: float) -> float:
        """Rounds a MS timestamp down to the nearest timeframe bin."""
        ts_sec = tsMs / 1000.0
        binned = (int(ts_sec) // self.timeframe) * self.timeframe
        return float(binned)

    def process_trade(self, tsMs: float, price: float, sz: float, is_buy: bool) -> Optional[Candle]:
        """
        Processes a raw tick.
        Returns a finalized Candle object ONLY if the current trade caused the candle to roll over.
        """
        bin_start = self._get_bin_timestamp(tsMs)
        
        finished_candle = None
        
        # Initialization
        if self.current_candle is None:
            self.current_candle = Candle(bin_start, price, self.tick_size)
            
        # Rollover check
        elif bin_start > self.current_candle.start_time:
            # The current tick belongs to a new time period. Finalize the old one.
            self.current_candle.finalize()
            self.closed_candles.append(self.current_candle)
            
            # Maintain memory limit
            if len(self.closed_candles) > self.max_history:
                self.closed_candles.pop(0)
                
            finished_candle = self.current_candle
            
            # Start the new candle
            self.current_candle = Candle(bin_start, price, self.tick_size)
            
        # Add trade to the active candle
        self.current_candle.add_trade(price, sz, is_buy)
        
        return finished_candle
        
    def get_highest_high(self, lookback: int) -> float:
        """Returns the highest High in the last N closed candles."""
        if not self.closed_candles:
            return 0.0
        relevant = self.closed_candles[-lookback:]
        return max([c.high for c in relevant])
        
    def get_lowest_low(self, lookback: int) -> float:
        """Returns the lowest Low in the last N closed candles."""
        if not self.closed_candles:
            return float('inf')
        relevant = self.closed_candles[-lookback:]
        return min([c.low for c in relevant])
        
    def get_last_completed(self) -> Optional[Candle]:
        if not self.closed_candles:
            return None
        return self.closed_candles[-1]
