from typing import Dict, Optional

class VolumeProfileBuilder:
    """
    Maintains a price-binned volume profile for an individual time period (e.g., 1 minute).
    Calculates the exact Point of Control (POC).
    """
    
    def __init__(self, tick_size: float = 1.0):
        # We bin prices to the nearest tick_size to construct the histogram
        self.tick_size = tick_size
        self.volume_at_price: Dict[float, float] = {}
        self.total_volume = 0.0

    def add_trade(self, price: float, volume: float):
        """Quantizes the price and adds volume to that price bucket."""
        # Find the nearest bin
        binned_price = round(price / self.tick_size) * self.tick_size
        
        if binned_price not in self.volume_at_price:
            self.volume_at_price[binned_price] = 0.0
            
        self.volume_at_price[binned_price] += volume
        self.total_volume += volume

    def get_poc(self) -> Optional[float]:
        """Returns the price with the highest traded volume (POC)."""
        if not self.volume_at_price:
            return None
            
        # Find the key (price) with the highest value (volume)
        poc_price = max(self.volume_at_price.items(), key=lambda x: x[1])[0]
        return poc_price
        
    def get_poc_volume(self) -> float:
        """Returns the volume executed exactly at the POC."""
        poc = self.get_poc()
        if poc is None:
            return 0.0
        return self.volume_at_price[poc]

    def is_upper_half(self, poc: float, high: float, low: float) -> bool:
        """Helper to determine if POC is in the top 50% of the candle's range."""
        midpoint = (high + low) / 2.0
        return poc > midpoint
