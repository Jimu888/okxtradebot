---
name: okx-compound-strategy
description: >
  AI-driven compound trading strategy with multi-dimensional market assessment.
  Each cycle begins with a market context evaluation across volatility, sentiment,
  and capital flow dimensions before any trade decision is made.
  BTC-USDT-SWAP: 50x isolated, long-only. Entry confidence scored 0-10 using
  RSI+CCI+MFI+Supertrend+funding rate+long-short ratio+candlestick patterns.
  Only HIGH confidence (≥7) triggers full entry; MEDIUM (5-6) triggers half-size.
  RAVE-USDT-SWAP: dedicated short with multi-timeframe signal counting (optional).
  Grid bots: dual-scan using both price gainers and OI accumulation scanner,
  validated by sentiment, BBWidth volatility filter, and capital flow confirmation.
  All orders tagged agentTradeKit for leaderboard counting.
license: MIT
metadata:
  author: compound-strategy
  version: "3.0.0"
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
3. **Run market context assessment** — volatility + sentiment + capital flow
4. Run BTC strategy phase (AI confidence-scored entry)
5. Run RAVE dedicated short phase (optional, signal-gated)
6. Run volatility grid strategy phase (dual OI+price scan)
7. Save updated state to `state.json`

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

## PHASE 0.5 — Market Context Assessment (every cycle, before any trade)

Gather the following in parallel:

```bash
# Trend direction & strength
NODE_OPTIONS="--require /Users/jimu/.okx/proxy-inject.cjs" PATH="/opt/homebrew/opt/node@18/bin:$PATH" okx market indicator supertrend BTC-USDT-SWAP --bar 1H --profile tradebot
NODE_OPTIONS="--require /Users/jimu/.okx/proxy-inject.cjs" PATH="/opt/homebrew/opt/node@18/bin:$PATH" okx market indicator adx BTC-USDT-SWAP --bar 1H --profile tradebot

# Volatility regime
NODE_OPTIONS="--require /Users/jimu/.okx/proxy-inject.cjs" PATH="/opt/homebrew/opt/node@18/bin:$PATH" okx market indicator bbwidth BTC-USDT-SWAP --bar 1H --profile tradebot
NODE_OPTIONS="--require /Users/jimu/.okx/proxy-inject.cjs" PATH="/opt/homebrew/opt/node@18/bin:$PATH" okx market indicator hv BTC-USDT-SWAP --bar 1H --profile tradebot

# Capital flow
NODE_OPTIONS="--require /Users/jimu/.okx/proxy-inject.cjs" PATH="/opt/homebrew/opt/node@18/bin:$PATH" okx market indicator mfi BTC-USDT-SWAP --bar 1H --profile tradebot
NODE_OPTIONS="--require /Users/jimu/.okx/proxy-inject.cjs" PATH="/opt/homebrew/opt/node@18/bin:$PATH" okx market funding-rate BTC-USDT-SWAP --profile tradebot
NODE_OPTIONS="--require /Users/jimu/.okx/proxy-inject.cjs" PATH="/opt/homebrew/opt/node@18/bin:$PATH" okx market indicator top-long-short BTC-USDT-SWAP --profile tradebot

# Sentiment
NODE_OPTIONS="--require /Users/jimu/.okx/proxy-inject.cjs" PATH="/opt/homebrew/opt/node@18/bin:$PATH" okx news coin-sentiment --coins BTC --period 24h --profile tradebot
```

**AI must output a structured market context summary before proceeding:**

```
[MARKET CONTEXT]
Trend:      Supertrend={UP|DOWN}, ADX={value} → {trending if >25 / ranging if <20}
Volatility: BBWidth={value}, HV={value} → {high/medium/low} volatility regime
Cap Flow:   MFI={value} → {inflow if >50 / outflow if <50}, Funding={value} → {long-biased/short-biased/neutral}
Positioning: Long={ratio}, Short={ratio} → {crowded longs/crowded shorts/balanced}
Sentiment:  BTC={bullish|neutral|bearish}, mentions={n}
Baseline:   Market is [description]. Overall confidence adjustment: [+1 / 0 / -1]
```

**Interpretation rules (AI applies judgment, not just thresholds):**
- Supertrend DOWN + ADX > 25 = strong downtrend → penalize BTC long confidence by 2pts
- MFI < 30 = capital outflow despite price drop → potential capitulation → boost long confidence 1pt
- Funding rate persistently negative (< -0.01%) = shorts dominating, squeeze risk → boost long confidence 1pt
- Long/short ratio < 0.45 (crowded shorts) = contrarian bullish signal → boost long confidence 1pt
- BBWidth high + HV high = trending/breakout environment → good for directional trades, less ideal for grids
- BBWidth low + HV low = compression → grid bots perform well, directional trades less reliable

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

### Step 2B — Gather BTC Signals (multi-dimensional)

```bash
# Price momentum
NODE_OPTIONS="--require /Users/jimu/.okx/proxy-inject.cjs" PATH="/opt/homebrew/opt/node@18/bin:$PATH" okx market indicator RSI BTC-USDT-SWAP --period 14 --bar 5m --profile tradebot
NODE_OPTIONS="--require /Users/jimu/.okx/proxy-inject.cjs" PATH="/opt/homebrew/opt/node@18/bin:$PATH" okx market indicator CCI BTC-USDT-SWAP --period 20 --bar 5m --profile tradebot
NODE_OPTIONS="--require /Users/jimu/.okx/proxy-inject.cjs" PATH="/opt/homebrew/opt/node@18/bin:$PATH" okx market ticker BTC-USDT-SWAP --profile tradebot

# Volume-weighted capital flow
NODE_OPTIONS="--require /Users/jimu/.okx/proxy-inject.cjs" PATH="/opt/homebrew/opt/node@18/bin:$PATH" okx market indicator mfi BTC-USDT-SWAP --bar 5m --profile tradebot

# Candlestick reversal patterns
NODE_OPTIONS="--require /Users/jimu/.okx/proxy-inject.cjs" PATH="/opt/homebrew/opt/node@18/bin:$PATH" okx market indicator bull-engulf BTC-USDT-SWAP --bar 5m --profile tradebot
NODE_OPTIONS="--require /Users/jimu/.okx/proxy-inject.cjs" PATH="/opt/homebrew/opt/node@18/bin:$PATH" okx market indicator three-soldiers BTC-USDT-SWAP --bar 5m --profile tradebot
```

### Step 2C — BTC Entry Confidence Scoring

**Only if no active BTC position** (`state.btc_position.active == false`):

**Gate condition** (must pass to proceed): `rsi_5m < 35` AND `cci_5m < -80`
If gate fails → skip entry, output: "BTC entry gate not met: RSI={value}, CCI={value}. No oversold condition."

If gate passes, **score each dimension (0-10 total)**:

| Dimension | Condition | Points |
|-----------|-----------|--------|
| RSI depth | < 25 (deep oversold) | +3 / < 30 → +2 / < 35 → +1 |
| CCI depth | < -150 | +2 / < -100 → +1 |
| MFI (5m) | < 25 (heavy outflow = capitulation) | +2 / < 35 → +1 |
| Candlestick | bull-engulf OR three-soldiers detected | +1 |
| Market context | Baseline adjustment from Phase 0.5 | +1 / 0 / -1 |

**AI output required:**
```
[BTC ENTRY SCORE]
RSI={value} → {pts}pts | CCI={value} → {pts}pts | MFI={value} → {pts}pts
Pattern={detected/none} → {pts}pts | Context adj={+1/0/-1}pts
Total={score}/10

Decision: {ENTER FULL (≥7) / ENTER HALF (5-6) / SKIP (<5)}
Reasoning: [2-3 sentences explaining WHY this score, what the key factors are,
            what could go wrong, and why this is or isn't a good entry]
```

**Execution:**
- Score ≥ 7 → full entry (200 USDT margin)
- Score 5-6 → half entry (100 USDT margin)
- Score < 5 → skip

```bash
NODE_OPTIONS="--require /Users/jimu/.okx/proxy-inject.cjs" PATH="/opt/homebrew/opt/node@18/bin:$PATH" okx swap set-leverage --instId BTC-USDT-SWAP --lever 50 --mgnMode isolated --posSide long --profile tradebot
```

```
notional = margin_usdt * 50
ctVal = 0.01 BTC
sz = floor(notional / (btc_price * ctVal))
```

```bash
NODE_OPTIONS="--require /Users/jimu/.okx/proxy-inject.cjs" PATH="/opt/homebrew/opt/node@18/bin:$PATH" okx swap place --instId BTC-USDT-SWAP --side buy --ordType market \
  --sz {sz} --posSide long --tdMode isolated --tag agentTradeKit --profile tradebot
```

Update state: active=true, entry_count=1, avg_entry_price, total_sz, remaining_pct=100.

**Second entry** (entry_count==1, next oversold signal with score ≥ 5): place same sz, update weighted avg.

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

### Step 2.5B2 — Keltner Channel Rebound Add-on (5m, replaces Vegas Channel)

**Only if `state.rave_position.active == true`** AND budget has room AND `state.rave_position.vegas_addon_count < 3`:

```bash
# 5m Keltner Channel (EMA-based, similar to Vegas Channel logic)
NODE_OPTIONS="--require /Users/jimu/.okx/proxy-inject.cjs" PATH="/opt/homebrew/opt/node@18/bin:$PATH" okx market indicator keltner RAVE-USDT-SWAP --bar 5m --profile tradebot
NODE_OPTIONS="--require /Users/jimu/.okx/proxy-inject.cjs" PATH="/opt/homebrew/opt/node@18/bin:$PATH" okx market ticker RAVE-USDT-SWAP --profile tradebot
```

Parse: `upper`, `middle`, `lower` from Keltner response.

**Keltner Middle Rebound condition** (all must be true):
1. `rave_price >= middle * 0.99` AND `rave_price <= middle * 1.01` — price touching middle band (±1%)
2. `rave_price < state.rave_position.avg_entry_price` — still below entry (profit zone)
3. Budget has room: `current_margin < rave_budget_limit`

**AI Reasoning**: Current price={rave_price}, Keltner middle={middle}, upper={upper}, lower={lower}. Is price rebounding into the Keltner middle as resistance?

If all conditions met — add-on 40 USDT margin:
```
sz = floor(40 * effective_leverage / (rave_price * ctVal))  # RAVE effective lever = 3
```
```bash
NODE_OPTIONS="--require /Users/jimu/.okx/proxy-inject.cjs" PATH="/opt/homebrew/opt/node@18/bin:$PATH" okx swap place --instId RAVE-USDT-SWAP --side sell --ordType market \
  --sz {sz} --posSide short --tdMode isolated --tag agentTradeKit --profile tradebot
```

Recalculate avg_entry_price (weighted average). Update total_sz. Increment `state.rave_position.vegas_addon_count` by 1.

Note: vegas_addon_count resets to 0 when rave_position is cleared (TP or SL).

### Step 2.5B3 — VWAP Rebound Add-on (5m, replaces BB middle band)

**Only if `state.rave_position.active == true`** AND budget has room AND `state.rave_position.bb_addon_count < 3`:

```bash
# 5m VWAP as dynamic resistance reference
NODE_OPTIONS="--require /Users/jimu/.okx/proxy-inject.cjs" PATH="/opt/homebrew/opt/node@18/bin:$PATH" okx market indicator vwap RAVE-USDT-SWAP --bar 5m --profile tradebot
NODE_OPTIONS="--require /Users/jimu/.okx/proxy-inject.cjs" PATH="/opt/homebrew/opt/node@18/bin:$PATH" okx market ticker RAVE-USDT-SWAP --profile tradebot
```

Parse: `vwap` value from response.

**VWAP Rebound condition** (all must be true):
1. `rave_price >= vwap * 0.99` AND `rave_price <= vwap * 1.01` — price touching VWAP (±1%)
2. `rave_price < state.rave_position.avg_entry_price` — still below entry (profit zone)
3. Budget has room: `current_margin < rave_budget_limit`

**AI Reasoning**: Current price={rave_price}, VWAP={vwap}. Is price rebounding up to VWAP resistance from below?

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

**TP① — drop >= 48%** (if `remaining_pct == 100`):
```
close_sz = max(1, floor(state.rave_position.total_sz * 0.50))
```
Close 50% (at least 1 contract). Update `remaining_pct = 50`.
```bash
NODE_OPTIONS="--require /Users/jimu/.okx/proxy-inject.cjs" PATH="/opt/homebrew/opt/node@18/bin:$PATH" okx swap place --instId RAVE-USDT-SWAP --side buy --ordType market \
  --sz {close_sz} --posSide short --tdMode isolated --reduceOnly \
  --tag agentTradeKit --profile tradebot
```
Log: "RAVE TP1: closed 50% at {rave_price} (-{drop_pct:.1f}%)"

**TP② — drop >= 70%** (if `remaining_pct == 50`):
```
remaining_sz = max(1, floor(state.rave_position.total_sz * remaining_pct / 100))
```
Close all remaining. Clear rave_position from state.
```bash
NODE_OPTIONS="--require /Users/jimu/.okx/proxy-inject.cjs" PATH="/opt/homebrew/opt/node@18/bin:$PATH" okx swap place --instId RAVE-USDT-SWAP --side buy --ordType market \
  --sz {remaining_sz} --posSide short --tdMode isolated --reduceOnly \
  --tag agentTradeKit --profile tradebot
```
Log: "RAVE TP2: fully closed at {rave_price} (-{drop_pct:.1f}%)"

**TP③ — drop >= 90%** (safety net, close all if still open):
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

### Step 3A — Dual Candidate Scan

Run both scans in parallel:

**Scan A — Price Gainers:**
```bash
NODE_OPTIONS="--require /Users/jimu/.okx/proxy-inject.cjs" PATH="/opt/homebrew/opt/node@18/bin:$PATH" okx market tickers SWAP --profile tradebot
```
Sort by 24h change descending. Take top 10 (exclude RAVE). For each, call `okx market ticker {instId}` to get exact 24h change %.

**Scan B — OI Accumulation (capital flow signal):**
```bash
NODE_OPTIONS="--require /Users/jimu/.okx/proxy-inject.cjs" PATH="/opt/homebrew/opt/node@18/bin:$PATH" okx market oi-change --instType SWAP --bar 1H --sortBy oiDeltaPct --sortOrder desc --limit 10 --minVolUsd24h 500000 --profile tradebot
```
Returns tokens where large positions are being built in the last hour.

**Merge:** Tokens appearing in BOTH lists (price up AND OI up) are highest conviction. Single-list tokens are lower priority. Skip any already in `state.grid_bots`.

### Step 3B — Multi-Dimensional Candidate Validation

For each candidate token (process top 3 from merged scan):

```bash
# Technical: divergence detection
NODE_OPTIONS="--require /Users/jimu/.okx/proxy-inject.cjs" PATH="/opt/homebrew/opt/node@18/bin:$PATH" okx market indicator RSI {instId} --period 14 --bar 5m --profile tradebot
NODE_OPTIONS="--require /Users/jimu/.okx/proxy-inject.cjs" PATH="/opt/homebrew/opt/node@18/bin:$PATH" okx market indicator MACD {instId} --bar 5m --profile tradebot

# Volatility: is this a good grid environment?
NODE_OPTIONS="--require /Users/jimu/.okx/proxy-inject.cjs" PATH="/opt/homebrew/opt/node@18/bin:$PATH" okx market indicator bbwidth {instId} --bar 1H --profile tradebot
NODE_OPTIONS="--require /Users/jimu/.okx/proxy-inject.cjs" PATH="/opt/homebrew/opt/node@18/bin:$PATH" okx market indicator atr {instId} --bar 5m --profile tradebot

# Capital flow: confirm with MFI
NODE_OPTIONS="--require /Users/jimu/.okx/proxy-inject.cjs" PATH="/opt/homebrew/opt/node@18/bin:$PATH" okx market indicator mfi {instId} --bar 1H --profile tradebot
NODE_OPTIONS="--require /Users/jimu/.okx/proxy-inject.cjs" PATH="/opt/homebrew/opt/node@18/bin:$PATH" okx market funding-rate {instId} --profile tradebot

# Sentiment: is the market aware of this move?
NODE_OPTIONS="--require /Users/jimu/.okx/proxy-inject.cjs" PATH="/opt/homebrew/opt/node@18/bin:$PATH" okx news coin-sentiment --coins {baseCcy} --period 24h --profile tradebot
```

**Divergence detection:**
- **Bullish (底背离)** → LONG grid: price lower low + RSI higher low
- **Bearish (顶背离)** → SHORT grid: price higher high + RSI lower high
- **Neutral (no divergence)** → NEUTRAL grid if BBWidth confirms oscillation

**Grid Environment Score (AI output required for each candidate):**

```
[GRID CANDIDATE: {instId}]
Source:     {Price-gainers only / OI-scan only / BOTH (highest conviction)}
Divergence: {bullish/bearish/none} on 5m RSI
MACD:       {golden cross / death cross / neutral}
BBWidth:    {value} → {wide=trending, narrow=ranging, best grid: narrow/medium}
MFI(1H):    {value} → {capital inflow if >50 / outflow if <50}
Funding:    {value} → {interpretation}
Sentiment:  {bullish%} bullish, {mentions} mentions → {hot/normal/cold}

Score: {0-10}
Reasoning: [2-3 sentences: why enter or skip, what the edge is,
            what the risk is, how signals align or conflict]
Decision:   {DEPLOY GRID / SKIP}
Grid type:  {long / short / neutral}
Size:       {20/40/70/100 USDT based on score}
```

**Scoring guide:**
- Both scans (price + OI): +2pts
- RSI divergence confirmed: +2pts
- MACD confirms direction: +1pt
- MFI > 60 (inflow): +1pt
- Sentiment bullish > 0.5 AND mentions > 100: +1pt
- BBWidth suitable for grid type: +1pt
- Funding rate not extreme against position: +1pt
- Score ≥ 7 → deploy | 5-6 → deploy at half size | < 5 → skip

### Step 3C — Position Sizing

```
If total of existing grids + new > 100 USDT: skip this token.
Size by score:
  Score ≥ 8 → min(100, remaining_budget) USDT
  Score 6-7 → min(40, remaining_budget) USDT
  Score 5   → min(20, remaining_budget) USDT
```

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

## AI Reasoning Framework

Every cycle must produce structured reasoning output. This is not optional — it is the core of the strategy's value.

### Required outputs per cycle:

**1. Market Context Block** (Phase 0.5 output):
```
[MARKET CONTEXT {timestamp}]
Trend: ... | Volatility: ... | Cap Flow: ... | Positioning: ... | Sentiment: ...
Baseline: ... Overall confidence adjustment: ...
```

**2. Per-strategy Decision Block:**
```
[BTC DECISION]
Score: {n}/10 | Decision: ENTER/SKIP
Reasoning: {Why. What the setup looks like. What could go wrong.}

[GRID DECISION: {instId}]
Score: {n}/10 | Decision: DEPLOY/SKIP
Reasoning: {Why this token. What makes it different from others. What the risk is.}
```

**3. Cycle Summary:**
```
[CYCLE SUMMARY {timestamp}]
Actions taken: {list or "none"}
Positions: {BTC: ..., Grids: ...}
Next watch: {what to monitor next cycle}
```

### Reasoning quality guidelines:
- **Always compare signals**: "RSI=28 is deeply oversold, more so than CCI=-105 which barely crosses the threshold. MFI=22 confirms real selling pressure, not just price noise."
- **Always state what's missing**: "The setup would be stronger if Supertrend were also UP, but it's currently DOWN — this reduces conviction."
- **Always quantify risk**: "At 50x, a 2% adverse move hits liquidation. Current ATR(5m)=85 means normal volatility covers 0.11% — manageable."
- **Skip reasoning must be specific**: Never write just "conditions not met." Write why the specific values don't support action.

### Proven track record (live results):
- RAVE-USDT-SWAP short @ 22.062 (2026-04-18): closed at ~12.4, **realized +196 USDT** (~44% drop captured)

---

## Execution Order Summary

```
Every 5 minutes:
│
├─ 1. Load state.json
├─ 2. Account check (balance + positions + bots)
│
├─ 3. PHASE 0.5: Market Context Assessment ← NEW
│   ├─ Supertrend + ADX → trend direction & strength
│   ├─ BBWidth + HV → volatility regime
│   ├─ MFI + Funding + Long/Short ratio → capital flow & positioning
│   ├─ BTC sentiment → crowd behavior
│   └─ OUTPUT: structured market context + confidence baseline
│
├─ 4. PHASE 2: BTC Strategy
│   ├─ Not activated? → check 1H DIF → activate if near zero
│   ├─ No position? → multi-dimensional scoring (RSI+CCI+MFI+pattern+context)
│   │   ├─ Score ≥7 → full entry (200U) | Score 5-6 → half entry (100U) | <5 → skip
│   │   └─ OUTPUT: score breakdown + reasoning
│   └─ Has position? → check SL → check CCI TP1 → check RSI TP2
│
├─ 5. PHASE 2.5: RAVE Dedicated Short (optional, signal-gated)
│   ├─ No position? → scan 4H/1H/5m for bearish signals → enter if ≥1 signal
│   ├─ Has position? → check if new signals appeared → add-on if signal_count increased
│   └─ Has position? → check SL (above swing_high) → check TP1/TP2/TP3
│
├─ 6. PHASE 3: Grid Strategy ← ENHANCED
│   ├─ Dual scan: top-gainers (price) + oi-change (capital flow)
│   ├─ Merge: tokens in BOTH lists = highest conviction
│   ├─ Per-candidate: RSI divergence + MACD + BBWidth + MFI + sentiment scoring
│   ├─ Score-based sizing: ≥8→100U, 6-7→40U, 5→20U
│   ├─ OUTPUT: score breakdown + reasoning for each candidate
│   └─ Manage existing bots (SL / TP)
│
└─ 7. Save state.json + output cycle summary
```

---

## Edge Cases

- **BTC liquidation risk**: At 50x isolated, liquidation occurs ~2% adverse move. SL at -1.2% exits before liquidation.
- **RAVE price gap**: If RAVE gaps above swing_high, market close immediately on detection.
- **Insufficient balance**: If `free_usdt < 200`, skip new BTC entry. If `free_usdt < 20`, skip new grids.
- **Grid creation fails**: Log error, try next token in top-5.
- **state.json missing**: Initialize with default empty state and proceed.
- **Missing tag**: ALWAYS include `--tag agentTradeKit` on ALL swap place and bot grid create commands. This is required for leaderboard counting.
