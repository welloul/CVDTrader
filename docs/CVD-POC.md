# CVD-POC Delta Reversal Strategy

> **Documentation Rule:** Every feature, strategy, and component of this bot **MUST** be documented in the `/docs` folder. This file covers the Delta-POC Reversal strategy end-to-end — from indicator calculation through entry signal generation to the CVD-based exit engine.

---

## Overview

The **Delta-POC Reversal** strategy is a mean-reversion approach that identifies price exhaustion or absorption at swing extremes, then fades the move using a Post-Only limit order placed at the Point of Control (POC) of the signal candle. The position is managed dynamically using Cumulative Volume Delta (CVD) behaviour on subsequent candles.

---

## 1. Indicator Definitions

### 1.1 Cumulative Volume Delta (CVD)

**File:** [`backend/src/market_data/indicators.py`](../backend/src/market_data/indicators.py), [`backend/src/market_data/candles.py`](../backend/src/market_data/candles.py)

CVD measures net buying vs. selling pressure by tracking the aggressor side of every trade.

**Formula (per trade tick):**
```
delta = +volume   if aggressor = buyer  (is_buy = True)
delta = -volume   if aggressor = seller (is_buy = False)
CVD  += delta     (cumulative sum)
```

**Two scopes of CVD are maintained:**
- **Global CVD** (`IndicatorCompute.cvd`): running total since bot start — used for long-term trend bias.
- **Per-candle CVD** (`Candle.cvd`): resets to 0.0 at the start of each 1-minute bar — used for strategy signal detection and exit management. This is the primary one the strategy uses.

A **positive per-candle CVD** means buyers dominated that bar.  
A **negative per-candle CVD** means sellers dominated that bar.

---

### 1.2 Point of Control (POC)

**File:** [`backend/src/market_data/profile.py`](../backend/src/market_data/profile.py)

The POC is the price level within a candle that attracted the highest traded volume. It is computed using a Volume Profile histogram.

**Algorithm:**
```
For every trade tick within the 1m candle:
    binned_price = round(price / tick_size) * tick_size   # quantize to $1 bins
    volume_at_price[binned_price] += trade_volume

When candle closes (candle.finalize()):
    POC = argmax(volume_at_price)   # price bin with the most volume
```

The POC represents the **fair value** or "price magnet" of that time period — the level where the market spent the most effort. This is the entry price for the strategy.

---

### 1.3 VWAP (Volume-Weighted Average Price)

**File:** [`backend/src/market_data/vwap.py`](../backend/src/market_data/vwap.py)

VWAP is a continuous anchor that resets at 00:00 UTC daily. It acts as the daily fair value filter:
- Price **above VWAP** = bullish bias → SHORT setups only
- Price **below VWAP** = bearish bias → LONG setups only

---

## 2. Signal Generation

**File:** [`backend/src/strategy/module.py`](../backend/src/strategy/module.py) — `_evaluate_signal()`

Signals are evaluated **on every 1-minute candle close.**

### 2.1 Pre-conditions (all must pass)

1. Bot is running (`state.is_running = True`)
2. No existing position or pending order for this coin
3. At least 3 closed candles of history exist
4. `curr.poc` is not `None`
5. The current candle sets a **new swing high or new swing low** vs. the previous 20 candles (`LOOKBACK = 20`)

### 2.2 Setup A — Exhaustion

```
abs(curr.cvd) < abs(prev.cvd) × 0.70
```

Price breaks to a new swing extreme but **buying/selling conviction dropped ≥ 30%** vs. the previous candle. The move is losing steam — latecomers are pushing price but the large players are stepping back.

`CVD_EXHAUSTION_RATIO = 0.70` (configurable constant at top of module)

### 2.3 Setup B — Absorption

```
curr_range < prev_range                    (candle body shrank — pace of move slowed)
AND
abs(curr.cvd) ≥ 90th percentile of        (but volume involvement is extreme)
    |CVD| over last 20 candles
```

Price breaks to a new extreme, the candle is physically smaller than the previous one, yet CVD is in the **top 10% of recent magnitudes**. This means large players are absorbing the directional move — buying into a new low or selling into a new high — stalling the trend.

`CVD_ABSORPTION_PCTILE = 0.90` (configurable)

---

## 3. Direction Filter (Flip Validation + VWAP)

After either setup fires, the strategy determines trade direction using **candle structure** and **VWAP**:

| Condition | Signal |
|---|---|
| `close < midpoint` AND `POC in upper half of range` AND `close > VWAP` AND `new high` | **SHORT** |
| `close > midpoint` AND `POC in lower half of range` AND `close < VWAP` AND `new low` | **LONG** |

**Rationale:**
- **SHORT setup**: If price broke to a new high but *closed back below the midpoint*, and the heaviest volume (POC) clustered in the upper half of the bar, buyers got trapped above the POC. Closing below VWAP would confirm the reversal but the filter requires close > VWAP to ensure we're shorting into *strength*, not chasing a breakdown.  
- **LONG setup**: Mirror logic — price broke to a new low, closed back above midpoint, heaviest volume in lower half → sellers trapped below POC. Filter requires close < VWAP (fading weakness above fair value).

---

## 4. Entry Execution

**File:** [`backend/src/strategy/module.py`](../backend/src/strategy/module.py) — `_try_enter_position()`

```
entry_price = curr.poc
size        = max_position_usd / entry_price   (e.g. $1000 / $67,000 ≈ 0.015 BTC)

# Post-Only (maker) offset — 0.1% inside the spread to avoid immediate fills
limit_px    = poc × 0.999   (BUY)
limit_px    = poc × 1.001   (SELL)

stop_loss   = curr.high + 2   (SHORT) — 2 ticks beyond the wick high
stop_loss   = curr.low  - 2   (LONG)  — 2 ticks below the wick low

take_profit = entry − (sl_dist × 1.5)  (SHORT)   — 1.5R reward
take_profit = entry + (sl_dist × 1.5)  (LONG)
```

**Execution modes:**
- `dryrun`: fill simulated immediately at POC price; position added directly to `GlobalState`
- `testnet` / `live`: Post-Only Limit order (`tif: "Alo"`) sent to Hyperliquid via `ExecutionGateway`

---

## 5. Exit Engine — CVD Trailing Stop

**File:** [`backend/src/strategy/module.py`](../backend/src/strategy/module.py) — `_manage_position_exit()`, `_check_sl_tp()`

The exit engine runs on two frequencies:

### 5.1 Tick-Level: Hard SL / TP Hit (`_check_sl_tp`)

Called on **every trade tick**. Closes immediately if:
- **Long**: `price ≤ stop_loss` OR `price ≥ take_profit`
- **Short**: `price ≥ stop_loss` OR `price ≤ take_profit`

### 5.2 Candle-Level: CVD Trailing Stop (`_manage_position_exit`)

Called on **every 1m candle close** while in a position.

The "favourable CVD sign" for a position:
- **LONG** → positive CVD (buyers in control)
- **SHORT** → negative CVD (sellers in control)

#### Rule 1 — CVD Declining
```
curr_sign == fav_sign   (CVD still aligned with position)
AND
abs(curr.cvd) < abs(prev.cvd)   (magnitude weakening)
```
Action: **Tighten SL to previous candle's POC** (SL only moves in the profitable direction — never widens).

#### Rule 2 — CVD Flip (1 hostile candle)
```
curr_sign != fav_sign   (CVD sign reversed — opposing pressure appeared)
```
Action: **Tighten SL to current candle's POC** + increment flip streak counter.

#### Rule 3 — Two Consecutive CVD Flips
```
flip_streak >= 2
```
Action: **Market close immediately** at current price. Two consecutive candles of opposing CVD indicates the reversal thesis has invalidated — the counter-move has gained structural conviction.

If CVD returns to the favourable sign, the flip streak resets to 0 and the position continues.

### 5.3 Exit Flow Diagram

```
Tick arrives
│
├─ SL hit?  → market close (SL)
├─ TP hit?  → market close (TP)
│
1m Candle closes
│
├─ CVD flip streak ≥ 2? → market close (2x hostile CVD)
├─ CVD flip (1 candle)?  → SL = current POC
└─ CVD declining?        → SL = previous POC
```

---

## 6. Position Lifecycle Summary

```
Signal detected on 1m candle close
  → _evaluate_signal()
  → _try_enter_position()
      limit order @ POC ± 0.1% (Post-Only)
      SL stored on Position object
      TP stored on Position object
      flip_streak[coin] = 0

Per tick:
  → update_simulated_pnl()
  → _check_sl_tp()
      if hit → _close_position()

Per candle close (while in position):
  → _manage_position_exit()
      Rule 1/2 → adjust stop_loss on Position
      Rule 3   → _close_position()

_close_position():
  → log PnL + reason
  → dryrun: del state.positions[coin]
  → live: gateway.close_position() → market_close()
  → reset flip_streak[coin]
```

---

## 7. Configurable Constants

| Constant | Default | Meaning |
|---|---|---|
| `LOOKBACK` | `20` | Candles used for swing high/low detection |
| `CVD_EXHAUSTION_RATIO` | `0.70` | CVD must fall to ≤70% of prev to qualify as exhaustion |
| `CVD_ABSORPTION_PCTILE` | `0.90` | CVD must be in top 10% of lookback magnitudes |
| `sl_offset` | `2` | Ticks beyond wick for initial stop-loss placement |
| Risk R-multiple | `1.5` | Take-profit = 1.5× the stop distance |

---

## 8. Known Limitations

1. **No partial closes**: the entire position is closed at once on exit trigger. A scaled-out approach (e.g., close 50% at 1R, trail rest) is not yet implemented.
2. **SL offset is in raw price units (ticks)**, not ATR-based. For low-priced coins (SOL at $83), `2` ticks = 2.4% — potentially wide. Consider ATR-scaled offset.
3. **Tick-size for POC bins is fixed at `$1`** — fine for BTC/ETH but too coarse for SOL. `VolumeProfileBuilder` accepts a configurable `tick_size`.
4. **Live order fill confirmation**: in live/testnet mode, the entry limit order is placed but position state is only updated via WebSocket `userData` feed, which is not yet wired. The strategy re-checks `state.positions` before entering, so duplicate entries won't occur, but the dashboard won't reflect the fill until the next state sync.
