---
name: okx-compound-strategy
description: >
  AI-driven compound trading strategy with multi-dimensional market assessment.
  Each cycle begins with Phase 0.5 market context (Supertrend, ADX, BBWidth, HV,
  MFI, funding rate, long/short ratio, sentiment) before any trade decision.
  BTC-USDT-SWAP: 50x isolated, long-only. Entry scored 0-100 across 7 weighted
  dimensions (RSI, CCI, MFI, Supertrend, L/S ratio, funding, candlestick).
  Score ≥70 → full entry 200U; 50-69 → half entry 100U; <50 → skip.
  AI must output structured scoring block + reasoning every cycle.
  RAVE-USDT-SWAP: dedicated short with multi-timeframe signal counting (optional).
  Grid bots: dual-scan (price gainers + OI accumulation), validated by 7-dimension
  100-point scoring. Score drives position sizing dynamically.
  All orders tagged agentTradeKit for leaderboard counting.
license: MIT
metadata:
  author: compound-strategy
  version: "3.2.0"
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
      "maxPx": 0,
      "minPx": 0,
      "sl_px": 0,
      "lever": 10,
      "sz": 0
    }
  ],
  "paused_grids": [
    {
      "instId": "",
      "direction": "",
      "maxPx": 0,
      "minPx": 0,
      "sl_px": 0,
      "lever": 10,
      "sz": 0,
      "resume_after": ""
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

### Step 2C — BTC Entry Weighted Scoring (total 100 pts)

**Only if no active BTC position** (`state.btc_position.active == false`):

**Gate condition** (must pass before scoring): `rsi_5m < 45` AND `cci_5m < -60`
Gate fails → output skip reason and stop. Gate passes → proceed to full scoring.

**Weighted scoring table:**

| # | Dimension | Weight | Scoring Rules |
|---|-----------|--------|---------------|
| 1 | RSI 5m (momentum depth) | **20 pts** | <30→20 / <35→16 / <40→12 / <45→6 / ≥45→0 |
| 2 | CCI 5m (oscillator depth) | **15 pts** | <-150→15 / <-100→12 / <-80→8 / <-60→4 / ≥-60→0 |
| 3 | MFI 5m (capital outflow) | **20 pts** | <30→20 / <40→15 / <50→8 / ≥50→0 |
| 4 | Supertrend 1H (trend) | **15 pts** | UP→15 / DOWN→0 |
| 5 | Long/Short ratio (positioning) | **10 pts** | short>65%→10 / short>55%→6 / balanced→3 / long>55%→0 |
| 6 | Funding rate (market bias) | **10 pts** | <-0.02%→10 / <-0.01%→7 / ±0.01%→4 / >0.02%→0 |
| 7 | Candlestick pattern (reversal) | **10 pts** | bull-engulf OR three-soldiers→10 / none→0 |

**Total = sum of all 7 dimensions = max 100 pts**

**AI must output the scoring block:**
```
[BTC入场加权评分]
① RSI={值}        → {分}/20分
② CCI={值}        → {分}/15分
③ MFI={值}        → {分}/20分
④ Supertrend={方向} → {分}/15分
⑤ 多空比=多{%}/空{%} → {分}/10分
⑥ 资金费率={值}    → {分}/10分
⑦ K线形态={结果}   → {分}/10分
──────────────────────────────
总分: {分}/100分

决策: {满仓入场≥70 / 半仓入场50-69 / 跳过<50}
保证金: {200U / 100U / 0U}
推理: [2-3句：哪些维度是关键支撑，哪些维度拖低了分数，
      当前市场状态下这笔交易的核心逻辑是什么，最大风险在哪里]
```

**Execution:**
- Score ≥ 70 → full entry, margin = 200 USDT
- Score 50–69 → half entry, margin = 100 USDT
- Score < 50 → skip

```bash
NODE_OPTIONS="--require /Users/jimu/.okx/proxy-inject.cjs" PATH="/opt/homebrew/opt/node@18/bin:$PATH" okx swap set-leverage --instId BTC-USDT-SWAP --lever 50 --mgnMode isolated --posSide long --profile tradebot
```
```
sz = floor(margin * 50 / (btc_price * 0.01))
```
```bash
NODE_OPTIONS="--require /Users/jimu/.okx/proxy-inject.cjs" PATH="/opt/homebrew/opt/node@18/bin:$PATH" okx swap place --instId BTC-USDT-SWAP --side buy --ordType market \
  --sz {sz} --posSide long --tdMode isolated --tag agentTradeKit --profile tradebot
```

Update state: active=true, entry_count=1, avg_entry_price, total_sz, remaining_pct=100.
**Second entry** (entry_count==1, next signal with score ≥ 50): place same sz, update weighted avg.

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

AI must output reasoning before executing:
```
[BTC TP① 推理]
CCI={值} 已超买，短期动量见顶。当前未实现盈亏={uPnL}U。
评估：{本次减仓20%的理由；若Supertrend仍UP可保留更多，若ADX走弱则应更激进减仓}
决策: 执行TP① 减仓20%
```

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

AI must output reasoning before executing:
```
[BTC TP② 推理]
RSI={值} 进入超买区间，上涨动能趋于枯竭。持仓均价={avg}，当前价={price}，盈利={profit_pct:.1f}%。
评估：{资金费率、多空比是否支持继续持有；若出现背离信号说明；综合判断当前是否为合理出场点}
决策: 执行TP② 平全部剩余仓位
```

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

**Grid Candidate Weighted Scoring (total 100 pts):**

| # | Dimension | Weight | Scoring Rules |
|---|-----------|--------|---------------|
| 1 | 来源扫描 (signal source) | **20 pts** | 价格+OI双榜→20 / 仅OI榜→12 / 仅价格榜→8 |
| 2 | RSI背离 (divergence) | **20 pts** | 确认背离→20 / 弱背离→10 / 无→0 |
| 3 | MACD方向确认 | **15 pts** | 与方向一致→15 / 中性→5 / 反向→0 |
| 4 | MFI 1H (资金流向) | **15 pts** | >70→15 / 50-70→10 / 30-50→5 / <30→0 |
| 5 | BBWidth (网格适配度) | **10 pts** | 低/中震荡环境→10 / 强趋势→4 |
| 6 | 情绪 (sentiment) | **10 pts** | 看多>50%且热度>200→10 / 看多>40%且热度>100→6 / 中性→3 / 看空→0 |
| 7 | 资金费率 (funding) | **10 pts** | 正常±0.02%→10 / 极端正>0.05%→3 / 极端负<-0.05%→3 |

> **⚠️ 资金费率硬性拦截**：若 `abs(fundingRate) > 0.01`（即 >1%），**无论评分多高，强制跳过该标的**。
> 原因：1%/次 = 每天最高3%的资金成本，将快速侵蚀网格利润，不值得部署。

**AI must output for each candidate:**
```
[网格候选加权评分: {instId}]
① 来源={双榜/仅价格/仅OI}     → {分}/20分
② RSI背离={确认/弱/无}        → {分}/20分
③ MACD={金叉/死叉/中性}       → {分}/15分
④ MFI(1H)={值}                → {分}/15分
⑤ BBWidth={值}→{震荡/趋势}    → {分}/10分
⑥ 情绪={看多%}，{mentions}条  → {分}/10分
⑦ 资金费率={值}                → {分}/10分
──────────────────────────────
总分: {分}/100分

决策: {部署网格≥70 / 减量部署50-69 / 少量试仓30-49 / 跳过<30}
网格方向: {做多/做空/中性}
仓位: {按评分区间，见下表}
推理: [2-3句：哪些维度是核心驱动，信号之间是否有矛盾，
      盈利逻辑是什么，最大风险在哪里]
```

### Step 3C — Position Sizing by Score

```
预算检查：existing_grid_total + new_size ≤ 100 USDT，否则跳过。

按总分决定仓位：
  ≥ 70分 → min(remaining_budget, 70) USDT  (高置信度)
  50–69分 → min(remaining_budget, 40) USDT  (中等置信度)
  30–49分 → min(remaining_budget, 20) USDT  (低置信度，试仓)
  < 30分  → 跳过
```

### Step 3D — Grid Bot Creation

```bash
NODE_OPTIONS="--require /Users/jimu/.okx/proxy-inject.cjs" PATH="/opt/homebrew/opt/node@18/bin:$PATH" okx market indicator ATR {instId} --period 14 --bar 5m --profile tradebot
NODE_OPTIONS="--require /Users/jimu/.okx/proxy-inject.cjs" PATH="/opt/homebrew/opt/node@18/bin:$PATH" okx market ticker {instId} --profile tradebot
```

```
grid_min = current_price - (1.5 * atr)
grid_max = current_price + (1.5 * atr)

# Stop loss: outside grid range with 10% buffer
stop_loss_px = grid_min * 0.90   (for long/neutral grid)
stop_loss_px = grid_max * 1.10   (for short grid)
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

Save to state.grid_bots: algoId, instId, direction, maxPx={grid_max}, minPx={grid_min}, sl_px={stop_loss_px}, lever=10, sz={position_size}.

### Step 3E — Grid Bot Management (existing bots)

```bash
NODE_OPTIONS="--require /Users/jimu/.okx/proxy-inject.cjs" PATH="/opt/homebrew/opt/node@18/bin:$PATH" okx bot grid details --algoId {algoId} --algoOrdType contract_grid --profile tradebot
NODE_OPTIONS="--require /Users/jimu/.okx/proxy-inject.cjs" PATH="/opt/homebrew/opt/node@18/bin:$PATH" okx market ticker {instId} --profile tradebot
NODE_OPTIONS="--require /Users/jimu/.okx/proxy-inject.cjs" PATH="/opt/homebrew/opt/node@18/bin:$PATH" okx market funding-rate {instId} --profile tradebot
```

**⚠️ 资金费率规避（最高优先级，先于止损检查）**：
```
now = current_time
minutes_to_funding = (fundingTime - now) in minutes

if abs(fundingRate) > 0.01 AND minutes_to_funding <= 30:
    → 立即停止网格以规避本次资金费
    → 记录到state：paused_grid = {instId, algoId, direction, maxPx, minPx, sl_px, sz, resume_after: fundingTime + 10min}
    → 从state.grid_bots移除
    → 执行: okx bot grid stop --algoId {algoId} --algoOrdType contract_grid --profile tradebot
    → 日志: "FUNDING AVOID: 停止 {instId} 网格，资金费率={fundingRate:.3%}，结算时间={fundingTime}"

if instId in state.paused_grids AND now > resume_after:
    → 重建网格（使用原参数：direction, maxPx, minPx, sz）
    → 执行 Step 3D 创建逻辑
    → 移出 paused_grids，加入 grid_bots
    → 日志: "FUNDING RESUME: 重启 {instId} 网格"
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
Score: {n}/100 | Decision: ENTER FULL / ENTER HALF / SKIP
Reasoning: {Why. What the setup looks like. What could go wrong.}

[GRID DECISION: {instId}]
Score: {n}/100 | Decision: DEPLOY / REDUCED / PROBE / SKIP
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
│   ├─ No position? → 7-dimension 100-pt weighted scoring (RSI+CCI+MFI+Supertrend+L/S+funding+candle)
│   │   ├─ Score ≥70 → full entry (200U) | 50-69 → half entry (100U) | <50 → skip
│   │   └─ OUTPUT: per-dimension score breakdown + AI reasoning block
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
│   ├─ Per-candidate: 7-dimension 100-pt scoring (source+divergence+MACD+MFI+BBWidth+sentiment+funding)
│   ├─ Score-based sizing: ≥70→70U, 50-69→40U, 30-49→20U
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
