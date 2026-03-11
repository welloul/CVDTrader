import numpy as np
from collections import deque
from src.core.logger import log

class IndicatorCompute:
    """Computes technical indicators like CVD and RVOL using rolling buffers."""
    
    def __init__(self, window_size: int = 100):
        self.window_size = window_size
        self.reset()
        
    def reset(self):
        # CVD state
        self.cvd = 0.0
        self.cvd_history = deque(maxlen=self.window_size)
        
        # RVOL state (Rolling Volume)
        # Store (timestamp, volume) tuples to compute average volume over time
        self.volume_history = deque(maxlen=self.window_size)
        self.current_rvol = 1.0

    def update_cvd(self, is_buy: bool, volume: float) -> float:
        """Update Cumulative Volume Delta"""
        delta = volume if is_buy else -volume
        self.cvd += delta
        self.cvd_history.append(self.cvd)
        return self.cvd

    def update_rvol(self, timestamp: float, volume: float) -> float:
        """
        Update Relative Volume. 
        Calculates ratio of recent volume to historical average.
        """
        self.volume_history.append(volume)
        
        if len(self.volume_history) < self.window_size // 2:
            # Not enough data for meaningful RVOL
            self.current_rvol = 1.0
            return self.current_rvol
            
        # Simplified RVOL: current volume / average of window volume
        avg_vol = np.mean(list(self.volume_history)[:-1]) if len(self.volume_history) > 1 else volume
        if avg_vol > 0:
            self.current_rvol = volume / avg_vol
        else:
            self.current_rvol = 1.0
            
        return self.current_rvol
        
    def process_trade(self, timestamp: float, is_buy: bool, volume: float, price: float) -> dict:
        """Process a real-time trade tick and update indicators."""
        current_cvd = self.update_cvd(is_buy, volume)
        current_rvol = self.update_rvol(timestamp, volume)
        
        return {
            "cvd": current_cvd,
            "rvol": current_rvol,
            "price": price
        }
