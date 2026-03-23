import math
from typing import Dict, Any, Optional

class RoundingUtil:
    """Formats prices and sizes according to Hyperliquid Exchange specifications."""
    
    def __init__(self, meta_info: Any):
        """
        Initializes with exchange metadata.
        meta_info: The result of info_client.meta()
        """
        self.asset_info: Dict[str, Dict[str, Any]] = {}
        self._parse_meta(meta_info)

    def _parse_meta(self, meta_info: Any):
        if meta_info is None:
            # Use default values for common coins when meta is unavailable
            self.asset_info = {
                "BTC": {"sz_decimals": 2, "px_decimals": 2, "tick_size": 0.01},
                "ETH": {"sz_decimals": 4, "px_decimals": 2, "tick_size": 0.01},
                "SOL": {"sz_decimals": 2, "px_decimals": 2, "tick_size": 0.01},
            }
            return
            
        universe = meta_info.get("universe", [])
        for asset in universe:
            name = asset["name"]
            sz_decimals = asset["szDecimals"]
            # Get tick size from meta - it's usually in the "tickSize" field
            tick_size = asset.get("tickSize", 0.01)
            
            self.asset_info[name] = {
                "sz_decimals": sz_decimals,
                "tick_size": tick_size,
                # Keep px_decimals for size formatting
                "px_decimals": 5 - sz_decimals if (5 - sz_decimals) > 0 else 2 
            }

    def round_size(self, coin: str, sz: float) -> str:
        if coin not in self.asset_info:
            return str(sz) # Fallback
            
        decimals = self.asset_info[coin]["sz_decimals"]
        # Round down sizes to be safe
        factor = 10 ** decimals
        rounded = math.floor(sz * factor) / factor
        format_str = f"{{:.{decimals}f}}"
        return format_str.format(rounded)

    def round_price(self, coin: str, px: float) -> str:
        if coin not in self.asset_info:
            return str(px) # Fallback
            
        # Get tick size - this is required for Hyperliquid
        tick_size = self.asset_info[coin].get("tick_size", 0.01)
        
        # Round price to nearest tick size
        if tick_size > 0:
            rounded = round(px / tick_size) * tick_size
        else:
            rounded = px
        
        # Format with reasonable precision
        # Use enough decimal places to show the tick size precision
        if tick_size >= 1:
            return str(int(rounded))
        else:
            # Count decimal places needed for tick size
            decimals = len(str(tick_size).split('.')[-1].rstrip('0'))
            return f"{rounded:.{decimals}f}"

    def format_for_api(self, num: float) -> str:
        """Removes trailing zeros which HL API sometimes rejects"""
        s = str(num)
        if '.' in s:
            s = s.rstrip('0').rstrip('.')
        return s
