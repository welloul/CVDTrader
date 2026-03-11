# Strategy: Delta-POC Reversal

The "Delta-POC Reversal" strategy is an order-flow-centric approach designed to capture price reversals at points of extreme liquidity absorption or exhaustion.

## 1. Theoretical Basis

The strategy operates on the principle of **Trapped Liquidity**. When price makes a new high or low but fails to sustain the move despite significant volume, it indicates that "Aggressive" market participants are being absorbed by "Passive" limit orders. When price returns to this high-volume area (the Point of Control), those trapped traders often exit at break-even, creating the counter-momentum needed for a reversal.

## 2. Setup Conditions

The bot monitors 1-minute candles for two primary conditions:

### Condition A: Exhaustion
- **Price Action**: Makes a new swing high/low relative to the last 20 candles.
- **Volume Delta**: The absolute CVD of the current candle is at least 30% lower than the previous candle.
- **Significance**: Buyers or sellers are losing conviction at the extremes.

### Condition B: Absorption
- **Price Action**: Makes a new swing high/low but the price spread (High - Low) is smaller than the previous candle.
- **Volume**: CVD is in the top 10% of the last 20 candles.
- **Significance**: A massive "wall" of limit orders is absorbing all market orders, preventing price expansion.

## 3. Entry Logic

Once a setup is detected, the bot validates the "Flip" by checking:
1. **Market Structure Shift**: The candle must close as a reversal (long wick, body closing towards the mean).
2. **POC Placement**: The POC must be in the "upper half" of a candle for a short or "lower half" for a long.
3. **VWAP Filter**: 
    - **Long** only if price is BELOW the Daily VWAP.
    - **Short** only if price is ABOVE the Daily VWAP.

**Entry Point**: A Limit Order is placed exactly at the POC of the signal candle.

## 4. Exit & Risk Management

- **Stop Loss**: 1-2 ticks beyond the extreme wick of the signal candle.
- **Take Profit 1**: Target the POC of the impulse start or a 1:1.5 Risk/Reward.
- **Take Profit 2**: Trailing stop or 1:2 Risk/Reward.
- **TTL (Time-To-Live)**: Entry orders are automatically cancelled if not filled within 5 minutes (300 seconds).

## 5. Metadata Requirements

To execute this strategy, the bot requires:
- Tick-by-tick trade data via WebSocket.
- Precise price quantization (Tick Size) provided by the exchange metadata to build the Volume Profile.
