import math
from typing import Dict, Any

class RoundingUtil:
    """Formats prices and sizes according to Hyperliquid Exchange specifications."""
    
    def __init__(self, meta_info: Any):
        """
        Initializes with exchange metadata.
        meta_info: The result of info_client.meta()
        """
        self.asset_info: Dict[str, Dict[str, int]] = {}
        self._parse_meta(meta_info)

    def _parse_meta(self, meta_info: Any):
        universe = meta_info.get("universe", [])
        for asset in universe:
            name = asset["name"]
            sz_decimals = asset["szDecimals"]
            # Price decimals are usually 6 minus szDecimals, check SDK docs
            # Or fetched from a different part of the meta
            self.asset_info[name] = {
                "sz_decimals": sz_decimals,
                # Example rule for HL
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
            
        decimals = self.asset_info[coin]["px_decimals"]
        # Round to nearest
        rounded = round(px, decimals)
        
        # Determine sig figs needed by HL (often 5 sig figs max)
        # Simplified float formatting
        format_str = f"{{:.{decimals}f}}"
        return format_str.format(rounded)

    def format_for_api(self, num: float) -> str:
        """Removes trailing zeros which HL API sometimes rejects"""
        s = str(num)
        if '.' in s:
            s = s.rstrip('0').rstrip('.')
        return s
