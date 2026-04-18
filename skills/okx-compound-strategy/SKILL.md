---
name: okx-compound-strategy
description: >
  Compound trading strategy combining BTC trend trading, RAVE dedicated short,
  and high-volatility grid bots.
  BTC-USDT-SWAP: 50x isolated leverage, enter long on 5m RSI(14)<30 AND CCI(20)<-100,
  activated only after 1H MACD DIF crosses zero axis.
  RAVE-USDT-SWAP: dedicated short up to 200 USDT (uses BTC budget if BTC inactive),
  10x isolated, multi-timeframe bearish signals (4H/1H/30m/5m).
  High-volatility track: scan contract top-5 gainers for RSI/MACD divergence on 5m charts,
  deploy long/short contract grid bots with OI confirmation for position sizing.
  All orders tagged agentTradeKit for leaderboard counting.
license: MIT
metadata:
  author: compound-strategy
  version: "2.0.0"
  category: compound-strategy
  dependencies: okx-cex-market, okx-cex-trade, okx-cex-bot, okx-cex-portfolio
---

# OKX Compound Strategy

This skill depends on and orchestrates the following OKX official skills:
- **okx-cex-market** — market data, technical indicators, OI
- **okx-cex-trade** — perpetual swap order placement
- **okx-cex-bot** — contract grid bot management
- **okx-cex-portfolio** — account balance and positions

Install dependencies first:
```bash
npx skills add okx/agent-skills
```

**CRITICAL**: All order placement commands MUST include `--tag agentTradeKit` for leaderboard counting.

---

## Capital Allocation

| Strategy | Budget | Instrument | Leverage | Mode |
|----------|--------|------------|----------|------|
| BTC Trend | 400 USDT margin | BTC-USDT-SWAP | 50x isolated | Long-biased |
| RAVE Dedicated Short | Up to 200 USDT (uses BTC budget if BTC inactive) | RAVE-USDT-SWAP | 10x isolated | Short only |
| Volatility Grid | 100 USDT total | Top-5 gainer SWAPs | 10x isolated | Long or Short grid |

---

## When to Use This Skill

Execute this skill every 5 minutes. Each cycle:
1. Load persistent state from `state.json`
2. Run account check
3. Run BTC strategy phase
4. Run RAVE dedicated short phase
5. Run volatility grid strategy phase
6. Save updated state to `state.json`

All okx CLI commands must be run with:
```bash
NODE_OPTIONS="--require /Users/jimu/.okx/proxy-inject.cjs" PATH="/opt/homebrew/opt/node@18/bin:$PATH" okx ...
```

State file schema:
```json
{
  "btc_activated": false,
  "btc_position": {
    "active": false,
    "entry_count": 0,
    "avg_entry_price": 0,
    "total_sz": 0,
    "remaining_pct": 100
  },
  "rave_position": {
    "active": false,
    "avg_entry_price": 0,
    "total_sz": 0,
    "remaining_pct": 100,
    "signal_count": 0,
    "swing_high": 0,
    "vegas_addon_count": 0,
    "bb_addon_count": 0
  },
  "grid_bots": [
    {
      "algoId": "",
      "instId": "",
      "direction": "",
      "entry_oi": 0,
      "initial_sz": 0,
      "current_sz": 0,
      "stop_loss_px": 0,
      "divergence_high": 0,
      "divergence_low": 0
    }
  ]
}
```

---

## PHASE 1 — Account Check (every cycle, run first)

```bash
NODE_OPTIONS="--require /Users/jimu/.okx/proxy-inject.cjs" PATH="/opt/homebrew/opt/node@18/bin:$PATH" okx account balance --profile tradebot
NODE_OPTIONS="--require /Users/jimu/.okx/proxy-inject.cjs" PATH="/opt/homebrew/opt/node@18/bin:$PATH" okx account positions --profile tradebot
NODE_OPTIONS="--require /Users/jimu/.okx/proxy-inject.cjs" PATH="/opt/homebrew/opt/node@18/bin:$PATH" okx bot grid orders --profile tradebot
```

Extract:
- `free_usdt`: available USDT in trading account
- `btc_pos`: BTC-USDT-SWAP position size, side, avg entry price, uPnL
- `rave_pos`: RAVE-USDT-SWAP position size, side, avg entry price, uPnL
- `active_grids`: list of running grid bots with algoId and instId

Reconcile with state.json. If a position exists on exchange but not in state, add it. If state shows active but exchange shows closed, clear it from state.

---

## PHASE 2 — BTC Strategy (400 USDT, 50x isolated)

### Step 2A — One-Time Activation Check

If `state.btc_activated == false`:

```bash
# Get 1H MACD for BTC
NODE_OPTIONS="--require /Users/jimu/.okx/proxy-inject.cjs" PATH="/opt/homebrew/opt/node@18/bin:$PATH" okx market indicator MACD BTC-USDT-SWAP --bar 1H --profile tradebot
```

Parse the DIF line (fast line) value from the response.
- If `abs(DIF) <= 50` (DIF is near zero): set `state.btc_activated = true`, proceed to Step 2B
- Otherwise: **skip entire Phase 2 this cycle**. Log: "BTC strategy not yet activated. 1H DIF = {value}, waiting for zero-cross."

If `state.btc_activated == true`: always proceed to Step 2B.

### Step 2B — Gather BTC Signals

```bash
NODE_OPTIONS="--require /Users/jimu/.okx/proxy-inject.cjs" PATH="/opt/homebrew/opt/node@18/bin:$PATH" okx market indicator RSI BTC-USDT-SWAP --period 14 --bar 5m --profile tradebot
NODE_OPTIONS="--require /Users/jimu/.okx/proxy-inject.cjs" PATH="/opt/homebrew/opt/node@18/bin:$PATH" okx market indicator CCI BTC-USDT-SWAP --period 20 --bar 5m --profile tradebot
NODE_OPTIONS="--require /Users/jimu/.okx/proxy-inject.cjs" PATH="/opt/homebrew/opt/node@18/bin:$PATH" okx market ticker BTC-USDT-SWAP --profile tradebot
```

Extract: `rsi_5m`, `cci_5m`, `btc_price`

### Step 2C — BTC Entry Logic

**Only if no active BTC position** (`state.btc_position.active == false`):

Oversold condition: `rsi_5m < 30` AND `cci_5m < -100`

If condition met:
```bash
NODE_OPTIONS="--require /Users/jimu/.okx/proxy-inject.cjs" PATH="/opt/homebrew/opt/node@18/bin:$PATH" okx swap set-leverage --instId BTC-USDT-SWAP --lever 50 --mgnMode isolated --posSide long --profile tradebot
NODE_OPTIONS="--require /Users/jimu/.okx/proxy-inject.cjs" PATH="/opt/homebrew/opt/node@18/bin:$PATH" okx market instruments --instType SWAP --instId BTC-USDT-SWAP --profile tradebot
```

Calculate for 50% of 400 USDT = 200 USDT margin:
```
notional = 200 * 50 = 10,000 USDT
ctVal = 0.01 BTC (standard BTC-USDT-SWAP contract)
sz = floor(notional / (btc_price * ctVal))
```

```bash
NODE_OPTIONS="--require /Users/jimu/.okx/proxy-inject.cjs" PATH="/opt/homebrew/opt/node@18/bin:$PATH" okx swap place --instId BTC-USDT-SWAP --side buy --ordType market \
  --sz {sz} --posSide long --tdMode isolated --tag agentTradeKit --profile tradebot
```

Update state btc_position (active=true, entry_count=1, avg_entry_price, total_sz, remaining_pct=100).

**If `state.btc_position.entry_count == 1`** — on next oversold signal:
```bash
NODE_OPTIONS="--require /Users/jimu/.okx/proxy-inject.cjs" PATH="/opt/homebrew/opt/node@18/bin:$PATH" okx swap place --instId BTC-USDT-SWAP --side buy --ordType market \
  --sz {sz} --posSide long --tdMode isolated --tag agentTradeKit --profile tradebot
```
Recalculate weighted average entry price. Update state entry_count=2.

### Step 2D — BTC Exit Logic

**Only if active BTC position** (`state.btc_position.active == true`):

```bash
NODE_OPTIONS="--require /Users/jimu/.okx/proxy-inject.cjs" PATH="/opt/homebrew/opt/node@18/bin:$PATH" okx market indicator RSI BTC-USDT-SWAP --period 14 --bar 5m --profile tradebot
NODE_OPTIONS="--require /Users/jimu/.okx/proxy-inject.cjs" PATH="/opt/homebrew/opt/node@18/bin:$PATH" okx market indicator CCI BTC-USDT-SWAP --period 20 --bar 5m --profile tradebot
NODE_OPTIONS="--require /Users/jimu/.okx/proxy-inject.cjs" PATH="/opt/homebrew/opt/node@18/bin:$PATH" okx market ticker BTC-USDT-SWAP --profile tradebot
```

**Stop Loss** — highest priority:
```
sl_price = state.btc_position.avg_entry_price * (1 - 0.012)
```
If `btc_price <= sl_price`:
```bash
NODE_OPTIONS="--require /Users/jimu/.okx/proxy-inject.cjs" PATH="/opt/homebrew/opt/node@18/bin:$PATH" okx swap place --instId BTC-USDT-SWAP --side sell --ordType market \
  --sz {state.btc_position.total_sz} --posSide long --tdMode isolated --reduceOnly \
  --tag agentTradeKit --profile tradebot
```
Clear btc_position from state.

**Take Profit ① — CCI > 100** (if `remaining_pct == 100`):
```
close_sz = floor(state.btc_position.total_sz * 0.20)
```
```bash
NODE_OPTIONS="--require /Users/jimu/.okx/proxy-inject.cjs" PATH="/opt/homebrew/opt/node@18/bin:$PATH" okx swap place --instId BTC-USDT-SWAP --side sell --ordType market \
  --sz {close_sz} --posSide long --tdMode isolated --reduceOnly \
  --tag agentTradeKit --profile tradebot
```
Update `remaining_pct = 80`.

**Take Profit ② — RSI > 70** (close ALL remaining):
```
remaining_sz = floor(state.btc_position.total_sz * remaining_pct / 100)
```
```bash
NODE_OPTIONS="--require /Users/jimu/.okx/proxy-inject.cjs" PATH="/opt/homebrew/opt/node@18/bin:$PATH" okx swap place --instId BTC-USDT-SWAP --side sell --ordType market \
  --sz {remaining_sz} --posSide long --tdMode isolated --reduceOnly \
  --tag agentTradeKit --profile tradebot
```
Clear btc_position from state.

---

## PHASE 2.5 — RAVE Dedicated Short (up to 200 USDT, 10x isolated)

**Budget rule**: If `state.btc_position.active == false`, RAVE may use up to 200 USDT. Otherwise max 100 USDT.

### Step 2.5A — Multi-Timeframe Bearish Signal Detection

Gather RAVE data across 4 timeframes:

```bash
# 4H signals
NODE_OPTIONS="--require /Users/jimu/.okx/proxy-inject.cjs" PATH="/opt/homebrew/opt/node@18/bin:$PATH" okx market indicator RSI RAVE-USDT-SWAP --period 14 --bar 4H --profile tradebot
NODE_OPTIONS="--require /Users/jimu/.okx/proxy-inject.cjs" PATH="/opt/homebrew/opt/node@18/bin:$PATH" okx market indicator MACD RAVE-USDT-SWAP --bar 4H --profile tradebot
NODE_OPTIONS="--require /Users/jimu/.okx/proxy-inject.cjs" PATH="/opt/homebrew/opt/node@18/bin:$PATH" okx market candles RAVE-USDT-SWAP --bar 4H --limit 20 --profile tradebot

# 1H signals
NODE_OPTIONS="--require /Users/jimu/.okx/proxy-inject.cjs" PATH="/opt/homebrew/opt/node@18/bin:$PATH" okx market indicator RSI RAVE-USDT-SWAP --period 14 --bar 1H --profile tradebot
NODE_OPTIONS="--require /Users/jimu/.okx/proxy-inject.cjs" PATH="/opt/homebrew/opt/node@18/bin:$PATH" okx market indicator MACD RAVE-USDT-SWAP --bar 1H --profile tradebot
NODE_OPTIONS="--require /Users/jimu/.okx/proxy-inject.cjs" PATH="/opt/homebrew/opt/node@18/bin:$PATH" okx market candles RAVE-USDT-SWAP --bar 1H --limit 20 --profile tradebot

# 5m signals
NODE_OPTIONS="--require /Users/jimu/.okx/proxy-inject.cjs" PATH="/opt/homebrew/opt/node@18/bin:$PATH" okx market indicator RSI RAVE-USDT-SWAP --period 14 --bar 5m --profile tradebot
NODE_OPTIONS="--require /Users/jimu/.okx/proxy-inject.cjs" PATH="/opt/homebrew/opt/node@18/bin:$PATH" okx market indicator MACD RAVE-USDT-SWAP --bar 5m --profile tradebot
NODE_OPTIONS="--require /Users/jimu/.okx/proxy-inject.cjs" PATH="/opt/homebrew/opt/node@18/bin:$PATH" okx market candles RAVE-USDT-SWAP --bar 5m --limit 20 --profile tradebot

# Current price
NODE_OPTIONS="--require /Users/jimu/.okx/proxy-inject.cjs" PATH="/opt/homebrew/opt/node@18/bin:$PATH" okx market ticker RAVE-USDT-SWAP --profile tradebot
```

**Bearish signals to detect** (any ONE is sufficient to trigger initial entry):

1. **RSI Bearish Divergence (any TF)**: On the last 20 candles, find two swing highs. If price swing_high_2 > swing_high_1 (higher high) but RSI at swing_high_2 < RSI at swing_high_1 (lower RSI) → bearish divergence confirmed.

2. **MACD Death Cross (any TF)**: DIF crosses below DEA on the most recent candle → death cross signal.

3. **MACD Bearish Divergence (any TF)**: Two DIF/DEA crossover points. If crossover_2_DIF < crossover_1_DIF but price made higher high → MACD bearish divergence.

4. **Top Fractal (顶分型)**: In 4H or 1H candles, find a 3-candle pattern where middle candle has the highest high → fractal top formed.

5. **RSI Overbought (any TF)**: RSI > 70 after a major rally → potential reversal zone.

Count total number of bearish signals found across all timeframes: `signal_count`.

**Identify swing_high**: Find the highest price across the last 20 candles in the signal-triggering timeframe. This is the stop-loss reference level.

### Step 2.5B — RAVE Entry Logic

**If `state.rave_position.active == false` AND `signal_count >= 1`**:

```bash
NODE_OPTIONS="--require /Users/jimu/.okx/proxy-inject.cjs" PATH="/opt/homebrew/opt/node@18/bin:$PATH" okx swap set-leverage --instId RAVE-USDT-SWAP --lever 10 --mgnMode isolated --posSide short --profile tradebot
NODE_OPTIONS="--require /Users/jimu/.okx/proxy-inject.cjs" PATH="/opt/homebrew/opt/node@18/bin:$PATH" okx market instruments --instType SWAP --instId RAVE-USDT-SWAP --profile tradebot
```

Initial entry = 40 USDT margin:
```
notional = 40 * 10 = 400 USDT
sz = floor(notional / rave_price) — use ctVal from instruments response
```

```bash
NODE_OPTIONS="--require /Users/jimu/.okx/proxy-inject.cjs" PATH="/opt/homebrew/opt/node@18/bin:$PATH" okx swap place --instId RAVE-USDT-SWAP --side sell --ordType market \
  --sz {sz} --posSide short --tdMode isolated --tag agentTradeKit --profile tradebot
```

Update state:
```json
{
  "rave_position": {
    "active": true,
    "avg_entry_price": rave_price,
    "total_sz": sz,
    "remaining_pct": 100,
    "signal_count": signal_count,
    "swing_high": swing_high_price
  }
}
```

**If `state.rave_position.active == true` AND new signals detected** (signal_count > state.rave_position.signal_count):

Add-on position (scale in) with additional margin based on signal count:
- 2 signals: add 40 USDT margin
- 3+ signals: add 60 USDT margin (total up to budget limit)

Check budget limit first:
```
current_margin = state.rave_position.total_sz * state.rave_position.avg_entry_price / 10
addon_allowed = rave_budget - current_margin
```
If `addon_allowed <= 0`: skip add-on.

```bash
NODE_OPTIONS="--require /Users/jimu/.okx/proxy-inject.cjs" PATH="/opt/homebrew/opt/node@18/bin:$PATH" okx swap place --instId RAVE-USDT-SWAP --side sell --ordType market \
  --sz {addon_sz} --posSide short --tdMode isolated --tag agentTradeKit --profile tradebot
```

Recalculate avg_entry_price (weighted average). Update signal_count and total_sz.

### Step 2.5B2 — Vegas Channel Rebound Add-on (1m)

**Only if `state.rave_position.active == true`** AND budget has room AND `state.rave_position.vegas_addon_count < 3`:

```bash
# 1m Vegas Channel: EMA(144) = inner boundary, EMA(169) = outer boundary
NODE_OPTIONS="--require /Users/jimu/.okx/proxy-inject.cjs" PATH="/opt/homebrew/opt/node@18/bin:$PATH" okx market indicator EMA RAVE-USDT-SWAP --period 144 --bar 1m --profile tradebot
NODE_OPTIONS="--require /Users/jimu/.okx/proxy-inject.cjs" PATH="/opt/homebrew/opt/node@18/bin:$PATH" okx market indicator EMA RAVE-USDT-SWAP --period 169 --bar 1m --profile tradebot
NODE_OPTIONS="--require /Users/jimu/.okx/proxy-inject.cjs" PATH="/opt/homebrew/opt/node@18/bin:$PATH" okx market ticker RAVE-USDT-SWAP --profile tradebot
```

**Vegas Channel Rebound condition** (all must be true):
1. `rave_price >= ema_144` — price has rebounded up to at least the inner channel boundary
2. `rave_price <= ema_169 * 1.01` — price is at/near the channel, not broken far above it
3. `rave_price < state.rave_position.avg_entry_price` — price is still below our entry (still in profit zone for short)
4. Budget has room: `current_margin < rave_budget_limit`

**AI Reasoning**: Current price={rave_price}, EMA144={ema_144}, EMA169={ema_169}. Is price touching the Vegas Channel from below? Is this a rebound into resistance?

If all conditions met — add-on 40 USDT margin:
```
notional = 40 * leverage (use current effective leverage, typically 3x for RAVE)
sz = floor(notional / (rave_price * ctVal))
```
```bash
NODE_OPTIONS="--require /Users/jimu/.okx/proxy-inject.cjs" PATH="/opt/homebrew/opt/node@18/bin:$PATH" okx swap place --instId RAVE-USDT-SWAP --side sell --ordType market \
  --sz {sz} --posSide short --tdMode isolated --tag agentTradeKit --profile tradebot
```

Recalculate avg_entry_price (weighted average). Update total_sz.
Increment `state.rave_position.vegas_addon_count` by 1.

Note: vegas_addon_count resets to 0 when rave_position is cleared (TP or SL).

### Step 2.5B3 — BB Middle Band Rebound Add-on (1m)

**Only if `state.rave_position.active == true`** AND budget has room AND `state.rave_position.bb_addon_count < 3`:

```bash
# 1m Bollinger Bands (20, 2) — middle band = SMA(20)
NODE_OPTIONS="--require /Users/jimu/.okx/proxy-inject.cjs" PATH="/opt/homebrew/opt/node@18/bin:$PATH" okx market indicator BOLL RAVE-USDT-SWAP --period 20 --bar 1m --profile tradebot
NODE_OPTIONS="--require /Users/jimu/.okx/proxy-inject.cjs" PATH="/opt/homebrew/opt/node@18/bin:$PATH" okx market ticker RAVE-USDT-SWAP --profile tradebot
```

Parse response: `mid` = middle band (SMA20), `upper` = upper band, `lower` = lower band.

**BB Midline Rebound condition** (all must be true):
1. `rave_price >= mid * 0.99` AND `rave_price <= mid * 1.01` — price is touching/at the middle band (±1% tolerance)
2. `rave_price < state.rave_position.avg_entry_price` — still in profit zone for short
3. Budget has room: `current_margin < rave_budget_limit`
4. This cycle's price came from below mid (rebounding up, not falling through it) — check that previous price < mid

**AI Reasoning**: Current price={rave_price}, BB_mid={mid}, BB_upper={upper}, BB_lower={lower}. Is price touching the BB middle band as resistance? Is it rebounding into it from below?

If all conditions met — add-on 40 USDT margin:
```bash
NODE_OPTIONS="--require /Users/jimu/.okx/proxy-inject.cjs" PATH="/opt/homebrew/opt/node@18/bin:$PATH" okx swap place --instId RAVE-USDT-SWAP --side sell --ordType market \
  --sz {sz} --posSide short --tdMode isolated --tag agentTradeKit --profile tradebot
```

Recalculate avg_entry_price. Update total_sz. Increment `state.rave_position.bb_addon_count` by 1.

Note: bb_addon_count resets to 0 when rave_position is cleared.

### Step 2.5C — RAVE Exit Logic

**Only if `state.rave_position.active == true`**:

```bash
NODE_OPTIONS="--require /Users/jimu/.okx/proxy-inject.cjs" PATH="/opt/homebrew/opt/node@18/bin:$PATH" okx market ticker RAVE-USDT-SWAP --profile tradebot
```

**Stop Loss — highest priority**:
If `rave_price >= state.rave_position.swing_high`:
```bash
NODE_OPTIONS="--require /Users/jimu/.okx/proxy-inject.cjs" PATH="/opt/homebrew/opt/node@18/bin:$PATH" okx swap place --instId RAVE-USDT-SWAP --side buy --ordType market \
  --sz {state.rave_position.total_sz} --posSide short --tdMode isolated --reduceOnly \
  --tag agentTradeKit --profile tradebot
```
Clear rave_position from state. Log: "RAVE STOP LOSS: price {rave_price} broke above swing_high {swing_high}"

**Take Profit calculation**:
```
drop_pct = (state.rave_position.avg_entry_price - rave_price) / state.rave_position.avg_entry_price * 100
```

**TP① — drop >= 50%** (if `remaining_pct == 100`):
```
close_sz = floor(state.rave_position.total_sz * 0.30)
```
```bash
NODE_OPTIONS="--require /Users/jimu/.okx/proxy-inject.cjs" PATH="/opt/homebrew/opt/node@18/bin:$PATH" okx swap place --instId RAVE-USDT-SWAP --side buy --ordType market \
  --sz {close_sz} --posSide short --tdMode isolated --reduceOnly \
  --tag agentTradeKit --profile tradebot
```
Update `remaining_pct = 70`. Log: "RAVE TP1: closed 30% at {rave_price} (-{drop_pct:.1f}%)"

**TP② — drop >= 70%** (if `remaining_pct == 70`):
```
close_sz = floor(state.rave_position.total_sz * 0.40)
```
```bash
NODE_OPTIONS="--require /Users/jimu/.okx/proxy-inject.cjs" PATH="/opt/homebrew/opt/node@18/bin:$PATH" okx swap place --instId RAVE-USDT-SWAP --side buy --ordType market \
  --sz {close_sz} --posSide short --tdMode isolated --reduceOnly \
  --tag agentTradeKit --profile tradebot
```
Update `remaining_pct = 30`. Log: "RAVE TP2: closed 40% at {rave_price} (-{drop_pct:.1f}%)"

**TP③ — drop >= 90%** (close all remaining):
```
remaining_sz = floor(state.rave_position.total_sz * remaining_pct / 100)
```
```bash
NODE_OPTIONS="--require /Users/jimu/.okx/proxy-inject.cjs" PATH="/opt/homebrew/opt/node@18/bin:$PATH" okx swap place --instId RAVE-USDT-SWAP --side buy --ordType market \
  --sz {remaining_sz} --posSide short --tdMode isolated --reduceOnly \
  --tag agentTradeKit --profile tradebot
```
Clear rave_position from state. Log: "RAVE TP3: fully closed at {rave_price} (-{drop_pct:.1f}%)"

---

## PHASE 3 — High-Volatility Grid Strategy (100 USDT total, 10x isolated)

### Step 3A — Scan Top-5 Gainers

```bash
NODE_OPTIONS="--require /Users/jimu/.okx/proxy-inject.cjs" PATH="/opt/homebrew/opt/node@18/bin:$PATH" okx market tickers SWAP --profile tradebot
```

Sort all SWAP instruments by `change24h` descending. Select top 5 (exclude RAVE-USDT-SWAP — handled separately).
Skip any instrument already in `state.grid_bots`.

### Step 3B — Divergence Detection on Candidates

For each candidate token:

```bash
NODE_OPTIONS="--require /Users/jimu/.okx/proxy-inject.cjs" PATH="/opt/homebrew/opt/node@18/bin:$PATH" okx market candles {instId} --bar 5m --limit 20 --profile tradebot
NODE_OPTIONS="--require /Users/jimu/.okx/proxy-inject.cjs" PATH="/opt/homebrew/opt/node@18/bin:$PATH" okx market indicator RSI {instId} --period 14 --bar 5m --limit 20 --profile tradebot
```

Find swing lows and highs in last 20 candles (local extrema with 2-candle neighbors).

**Bullish Divergence (底背离)** → LONG grid:
- Price: swing_low_2 < swing_low_1 (lower low)
- RSI: rsi_at_low_2 > rsi_at_low_1 (higher RSI)

**Bearish Divergence (顶背离)** → SHORT grid:
- Price: swing_high_2 > swing_high_1 (higher high)
- RSI: rsi_at_high_2 < rsi_at_high_1 (lower RSI)

### Step 3C — OI Check and Position Sizing

```bash
NODE_OPTIONS="--require /Users/jimu/.okx/proxy-inject.cjs" PATH="/opt/homebrew/opt/node@18/bin:$PATH" okx market open-interest --instType SWAP --instId {instId} --profile tradebot
NODE_OPTIONS="--require /Users/jimu/.okx/proxy-inject.cjs" PATH="/opt/homebrew/opt/node@18/bin:$PATH" okx market indicator MACD {instId} --bar 5m --limit 20 --profile tradebot
```

`oi_pct_change = (current_oi - entry_oi) / entry_oi * 100`

**Position size table:**

| Signals | OI change | Size |
|---------|-----------|------|
| RSI divergence only | < 10% | 20 USDT |
| RSI divergence only | ≥ 10% | 30 USDT |
| RSI + MACD divergence | < 10% | 40 USDT |
| RSI + MACD divergence | ≥ 10% | 100 USDT (exclusive, close other bots first) |

If total of existing grids + new > 100 USDT: skip this token.

### Step 3D — Grid Bot Creation

```bash
NODE_OPTIONS="--require /Users/jimu/.okx/proxy-inject.cjs" PATH="/opt/homebrew/opt/node@18/bin:$PATH" okx market indicator ATR {instId} --period 14 --bar 5m --profile tradebot
NODE_OPTIONS="--require /Users/jimu/.okx/proxy-inject.cjs" PATH="/opt/homebrew/opt/node@18/bin:$PATH" okx market ticker {instId} --profile tradebot
```

```
grid_min = current_price - (1.5 * atr)
grid_max = current_price + (1.5 * atr)
```

```bash
NODE_OPTIONS="--require /Users/jimu/.okx/proxy-inject.cjs" PATH="/opt/homebrew/opt/node@18/bin:$PATH" okx swap set-leverage --instId {instId} --lever 10 --mgnMode isolated --profile tradebot

NODE_OPTIONS="--require /Users/jimu/.okx/proxy-inject.cjs" PATH="/opt/homebrew/opt/node@18/bin:$PATH" okx bot grid create \
  --instId {instId} \
  --algoOrdType contract_grid \
  --minPx {grid_min} \
  --maxPx {grid_max} \
  --gridNum 10 \
  --direction {long|short} \
  --lever 10 \
  --sz {position_size} \
  --tag agentTradeKit \
  --profile tradebot
```

Save to state.grid_bots with algoId, instId, direction, entry_oi, initial_sz, current_sz, stop_loss_px.

### Step 3E — Grid Bot Management (existing bots)

```bash
NODE_OPTIONS="--require /Users/jimu/.okx/proxy-inject.cjs" PATH="/opt/homebrew/opt/node@18/bin:$PATH" okx bot grid details --algoId {algoId} --profile tradebot
NODE_OPTIONS="--require /Users/jimu/.okx/proxy-inject.cjs" PATH="/opt/homebrew/opt/node@18/bin:$PATH" okx market ticker {instId} --profile tradebot
```

**Stop Loss**: Long grid if `price < stop_loss_px`, Short grid if `price > stop_loss_px`:
```bash
NODE_OPTIONS="--require /Users/jimu/.okx/proxy-inject.cjs" PATH="/opt/homebrew/opt/node@18/bin:$PATH" okx bot grid stop --algoId {algoId} --profile tradebot
```

**Take Profit (stop + recreate with reduced sz)**:
- TP①: pnl ≥ +60% → reduce to 50% sz
- TP②: pnl ≥ +100% → reduce to 25% sz
- TP③: pnl ≥ +200% → stop completely

Grid recreation uses same commands as Step 3D with updated sz.

---

## AI Reasoning Step (Required for Competition)

Before executing any trade, explicitly state your reasoning:

1. **Market Assessment**: What are the current indicator values? (exact numbers)
2. **Signal Evaluation**: Which conditions are met? Which are not? Why does this trigger action?
3. **Risk Check**: Current account balance, existing positions, available budget?
4. **Decision**: Enter / Exit / Hold / Skip — and exactly why
5. **Action**: Execute the specific okx CLI command

Example reasoning log:
```
[CYCLE 2026-04-18 14:35] RAVE Strategy Check:
- 4H RSI: 72.3 (overbought, bearish signal ✓)
- 1H MACD: DIF just crossed below DEA (death cross ✓)
- 5m RSI divergence: swing_high_2=25.1 > swing_high_1=23.8, RSI_2=68 < RSI_1=74 (bearish ✓)
- Signal count: 3 → add-on entry triggered
- Current position: 1 contract @ 23.7848, remaining 100%
- Budget available: 120 USDT (BTC inactive)
- Action: Add-on 40 USDT margin short position
```

---

## Execution Order Summary

```
Every 5 minutes:
│
├─ 1. Load state.json
├─ 2. Account check (balance + positions + bots)
│
├─ 3. PHASE 2: BTC Strategy
│   ├─ Not activated? → check 1H DIF → activate if near zero
│   ├─ No position? → check 5m RSI+CCI → enter if oversold
│   ├─ 1 entry? → check 5m RSI+CCI → add second entry if oversold
│   └─ Has position? → check SL → check CCI TP1 → check RSI TP2
│
├─ 4. PHASE 2.5: RAVE Dedicated Short
│   ├─ No position? → scan 4H/1H/5m for bearish signals → enter if ≥1 signal
│   ├─ Has position? → check if new signals appeared → add-on if signal_count increased
│   └─ Has position? → check SL (above swing_high) → check TP1/TP2/TP3
│
├─ 5. PHASE 3: Grid Strategy (exclude RAVE)
│   ├─ Scan top-5 gainers
│   ├─ Check divergence on candidates
│   ├─ Check OI + MACD for sizing
│   ├─ Create new grid bots (if budget available)
│   └─ Manage existing bots (SL / TP / add-on)
│
└─ 6. Save state.json
```

---

## Edge Cases

- **BTC liquidation risk**: At 50x isolated, liquidation occurs ~2% adverse move. SL at -1.2% exits before liquidation.
- **RAVE price gap**: If RAVE gaps above swing_high, market close immediately on detection.
- **Insufficient balance**: If `free_usdt < 200`, skip new BTC entry. If `free_usdt < 20`, skip new grids.
- **Grid creation fails**: Log error, try next token in top-5.
- **state.json missing**: Initialize with default empty state and proceed.
- **Missing tag**: ALWAYS include `--tag agentTradeKit` on ALL swap place and bot grid create commands. This is required for leaderboard counting.
