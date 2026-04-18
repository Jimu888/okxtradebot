---
name: okx-compound-strategy
description: >
  Compound trading strategy combining BTC trend trading and high-volatility grid bots.
  BTC-USDT-SWAP: 50x isolated leverage, enter long on 5m RSI(14)<30 AND CCI(20)<-100,
  scale in on second signal, exit on RSI>70 or CCI>100. High-volatility track: scan
  contract top-5 gainers for RSI/MACD divergence on 5m charts, deploy long/short
  contract grid bots with OI confirmation for position sizing. Uses okx-cex-market,
  okx-cex-trade, okx-cex-bot, okx-cex-portfolio skills.
license: MIT
metadata:
  author: compound-strategy
  version: "1.0.0"
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

---

## Capital Allocation

| Strategy | Budget | Instrument | Leverage | Mode |
|----------|--------|------------|----------|------|
| BTC Trend | 400 USDT margin | BTC-USDT-SWAP | 50x isolated | Long-biased |
| Volatility Grid | 100 USDT total | Top-5 gainer SWAPs | 10x isolated | Long or Short grid |

---

## When to Use This Skill

Execute this skill every 5 minutes. Each cycle:
1. Load persistent state from `state.json`
2. Run BTC strategy phase
3. Run volatility grid strategy phase
4. Save updated state to `state.json`

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
okx account balance --profile live
okx account positions --profile live
okx bot grid orders --profile live
```

Extract:
- `free_usdt`: available USDT in trading account
- `btc_pos`: BTC-USDT-SWAP position size, side, avg entry price, uPnL
- `active_grids`: list of running grid bots with algoId and instId

Reconcile with state.json. If a position exists in exchange but not in state, add it. If state shows active but exchange shows closed, clear it from state.

---

## PHASE 2 — BTC Strategy (400 USDT, 50x isolated)

### Step 2A — One-Time Activation Check

If `state.btc_activated == false`:

```bash
# Get 1H MACD for BTC
okx market indicator MACD BTC-USDT-SWAP --bar 1H
```

Parse the DIF line (fast line) value from the response.
- If `abs(DIF) <= 50` (DIF is near zero): set `state.btc_activated = true`, proceed to Step 2B
- Otherwise: **skip entire Phase 2 this cycle**. Log: "BTC strategy not yet activated. 1H DIF = {value}, waiting for zero-cross."

If `state.btc_activated == true`: always proceed to Step 2B.

### Step 2B — Gather BTC Signals

```bash
# 5m RSI(14)
okx market indicator RSI BTC-USDT-SWAP --period 14 --bar 5m

# 5m CCI(20)
okx market indicator CCI BTC-USDT-SWAP --period 20 --bar 5m

# Current price
okx market ticker BTC-USDT-SWAP
```

Extract current values:
- `rsi_5m`: current RSI value
- `cci_5m`: current CCI value
- `btc_price`: current mark price

### Step 2C — BTC Entry Logic

**Only if no active BTC position** (`state.btc_position.active == false`):

Oversold condition: `rsi_5m < 30` AND `cci_5m < -100`

If condition met:
```bash
# Set isolated leverage
okx swap set-leverage --instId BTC-USDT-SWAP --lever 50 --mgnMode isolated --profile live

# Get contract specs to calculate sz
okx market instruments --instType SWAP --instId BTC-USDT-SWAP
```

Calculate for 50% of 400 USDT = 200 USDT margin:
```
notional = 200 * 50 = 10,000 USDT
ctVal = 0.01 BTC (standard BTC-USDT-SWAP contract)
sz = floor(notional / (btc_price * ctVal))
```

```bash
okx swap place --instId BTC-USDT-SWAP --side buy --ordType market \
  --sz {sz} --posSide long --tdMode isolated --profile live
```

Update state:
```json
{
  "btc_position": {
    "active": true,
    "entry_count": 1,
    "avg_entry_price": btc_price,
    "total_sz": sz,
    "remaining_pct": 100
  }
}
```

Log: "BTC Entry 1/2: {sz} contracts at {btc_price}, margin 200 USDT, 50x isolated"

**If `state.btc_position.entry_count == 1`** (first entry exists, waiting for second):

If oversold condition met again:
```bash
# Add remaining 50% — another 200 USDT margin
# sz same calculation as above
okx swap place --instId BTC-USDT-SWAP --side buy --ordType market \
  --sz {sz} --posSide long --tdMode isolated --profile live
```

Recalculate average entry price:
```
new_avg = (entry1_price * sz1 + entry2_price * sz2) / (sz1 + sz2)
```

Update state:
```json
{
  "entry_count": 2,
  "avg_entry_price": new_avg,
  "total_sz": sz1 + sz2
}
```

### Step 2D — BTC Exit Logic

**Only if active BTC position exists** (`state.btc_position.active == true`):

```bash
okx market indicator RSI BTC-USDT-SWAP --period 14 --bar 5m
okx market indicator CCI BTC-USDT-SWAP --period 20 --bar 5m
okx market ticker BTC-USDT-SWAP
```

**Stop Loss** — check first, highest priority:
```
sl_price = state.btc_position.avg_entry_price * (1 - 0.012)
```
If `btc_price <= sl_price`:
```bash
okx swap place --instId BTC-USDT-SWAP --side sell --ordType market \
  --sz {state.btc_position.total_sz} --posSide long \
  --tdMode isolated --reduceOnly --profile live
```
Clear btc_position from state. Log: "BTC STOP LOSS triggered at {btc_price}, avg entry was {avg_entry_price}"

**Take Profit ① — CCI > 100** (if `remaining_pct == 100`):
If `cci_5m > 100`:
```
close_sz = floor(state.btc_position.total_sz * 0.20)
```
```bash
okx swap place --instId BTC-USDT-SWAP --side sell --ordType market \
  --sz {close_sz} --posSide long --tdMode isolated --reduceOnly --profile live
```
Update `state.btc_position.remaining_pct = 80`
Log: "BTC TP1: closed 20% at {btc_price} (CCI={cci_5m})"

**Take Profit ② — RSI > 70** (close ALL remaining):
If `rsi_5m > 70`:
```
remaining_sz = floor(state.btc_position.total_sz * state.btc_position.remaining_pct / 100)
```
```bash
okx swap place --instId BTC-USDT-SWAP --side sell --ordType market \
  --sz {remaining_sz} --posSide long --tdMode isolated --reduceOnly --profile live
```
Clear btc_position from state. Log: "BTC TP2: closed all remaining {remaining_pct}% at {btc_price} (RSI={rsi_5m})"

---

## PHASE 3 — High-Volatility Grid Strategy (100 USDT total, 10x isolated)

### Step 3A — Scan Top-5 Gainers

```bash
okx market tickers SWAP --json
```

From the JSON response, sort all SWAP instruments by `change24h` descending.
Select top 5 instruments. Extract their `instId` values (format: `TOKEN-USDT-SWAP`).

Skip any instrument already in `state.grid_bots`.

### Step 3B — Divergence Detection on Candidates

For each candidate token (not already in active grid bots):

```bash
# Get last 20 5m candles (OHLCV)
okx market candles {instId} --bar 5m --limit 20

# Get 5m RSI(14) — current and historical values
okx market indicator RSI {instId} --period 14 --bar 5m --limit 20
```

**Identify swing points in last 20 candles:**

Find the two most recent swing lows (local price minima) and swing highs (local price maxima).
A swing low = candle whose low is lower than the 2 candles on each side.
A swing high = candle whose high is higher than the 2 candles on each side.

**Bullish Divergence (底背离) — triggers LONG grid:**
- Price: swing_low_2 (more recent) < swing_low_1 (earlier) — price made lower low
- RSI: rsi_at_swing_low_2 > rsi_at_swing_low_1 — RSI made higher low
- Both swing lows must be within the last 20 candles

**Bearish Divergence (顶背离) — triggers SHORT grid:**
- Price: swing_high_2 (more recent) > swing_high_1 (earlier) — price made higher high
- RSI: rsi_at_swing_high_2 < rsi_at_swing_high_1 — RSI made lower high
- Both swing highs must be within the last 20 candles

If divergence detected, record:
- `divergence_type`: "bullish" or "bearish"
- `divergence_low`: the lower of the two swing lows (for bullish SL reference)
- `divergence_high`: the higher of the two swing highs (for bearish SL reference)

### Step 3C — OI Check and Position Sizing

For each token with divergence signal:

```bash
okx market open-interest --instType SWAP --instId {instId}
```

Record current OI as `current_oi`.

Determine `entry_oi` (OI at the time of divergence swing point):
- Use the OI value at the candle index of the more recent swing point
- If OI data not available at that point, use current OI as baseline

OI increase: `oi_pct_change = (current_oi - entry_oi) / entry_oi * 100`

**Check MACD divergence for add-on signal:**
```bash
okx market indicator MACD {instId} --bar 5m --limit 20
```

Identify the two most recent DIF/DEA crossover points within 20 candles.
- A crossover point = candle where DIF crosses DEA (from below for golden cross, from above for death cross)
- Record the MACD value (DIF value) at each crossover point

**MACD Bullish Divergence:** crossover_2_macd > crossover_1_macd BUT price made lower low → confirmed bullish
**MACD Bearish Divergence:** crossover_2_macd < crossover_1_macd BUT price made higher high → confirmed bearish

**Position size determination:**

| Signals present | OI increase | Position size |
|----------------|-------------|---------------|
| RSI divergence only | < 10% | 20 USDT |
| RSI divergence only | ≥ 10% | 30 USDT |
| RSI + MACD divergence | < 10% | 40 USDT |
| RSI + MACD divergence | ≥ 10% | 100 USDT (exclusive) |

If position size would be 100 USDT: close any existing second grid bot first, use full 100 USDT budget.
If total of existing grids + new position > 100 USDT: skip this token (budget exhausted).

### Step 3D — Grid Bot Creation

```bash
# Get ATR(14) on 5m
okx market indicator ATR {instId} --period 14 --bar 5m

# Get current price
okx market ticker {instId}
```

Calculate grid parameters:
```
center_price = current mark price
atr = ATR(14, 5m) value
grid_min = center_price - (1.5 * atr)
grid_max = center_price + (1.5 * atr)
grid_num = 10
```

For **bullish divergence** (LONG grid):
```bash
okx swap set-leverage --instId {instId} --lever 10 --mgnMode isolated --profile live

okx bot grid create \
  --instId {instId} \
  --algoOrdType contract_grid \
  --minPx {grid_min} \
  --maxPx {grid_max} \
  --gridNum 10 \
  --direction long \
  --lever 10 \
  --sz {position_size} \
  --profile live
```

For **bearish divergence** (SHORT grid):
```bash
okx swap set-leverage --instId {instId} --lever 10 --mgnMode isolated --profile live

okx bot grid create \
  --instId {instId} \
  --algoOrdType contract_grid \
  --minPx {grid_min} \
  --maxPx {grid_max} \
  --gridNum 10 \
  --direction short \
  --lever 10 \
  --sz {position_size} \
  --profile live
```

Save to state.grid_bots:
```json
{
  "algoId": "<returned algoId>",
  "instId": "{instId}",
  "direction": "long|short",
  "entry_oi": current_oi,
  "initial_sz": position_size,
  "current_sz": position_size,
  "stop_loss_px": divergence_low (for long) or divergence_high (for short),
  "divergence_high": swing_high_price,
  "divergence_low": swing_low_price,
  "has_macd_confirmed": true|false
}
```

### Step 3E — Grid Bot Management (existing bots)

For each bot in `state.grid_bots`:

```bash
okx bot grid details --algoId {algoId} --profile live
okx market ticker {instId}
```

Extract: `current_price`, `bot_pnl_pct` (unrealized PnL as % of initial investment)

**Stop Loss Check:**
- Long grid: if `current_price < state.stop_loss_px` → stop bot
- Short grid: if `current_price > state.stop_loss_px` → stop bot

```bash
okx bot grid stop --algoId {algoId} --profile live
```
Remove from state.grid_bots. Log: "Grid SL triggered: {instId} price={current_price} sl={stop_loss_px}"

**Take Profit — Partial Close (close portion of bot by reducing sz):**

TP①: `bot_pnl_pct >= 60%` AND `current_sz == initial_sz`:
- Target: reduce position to 50% of initial
- Stop bot, immediately recreate with same parameters but `sz = initial_sz * 0.50`
- Update `state.current_sz = initial_sz * 0.50`
- Log: "Grid TP1: {instId} +60%, reduced to 50% sz"

TP②: `bot_pnl_pct >= 100%` AND `current_sz == initial_sz * 0.50`:
- Target: reduce to 25% of initial
- Stop bot, recreate with `sz = initial_sz * 0.25`
- Update `state.current_sz = initial_sz * 0.25`
- Log: "Grid TP2: {instId} +100%, reduced to 25% sz"

TP③: `bot_pnl_pct >= 200%` AND `current_sz == initial_sz * 0.25`:
- Stop bot completely, do not recreate
```bash
okx bot grid stop --algoId {algoId} --profile live
```
Remove from state.grid_bots. Log: "Grid TP3: {instId} +200%, fully closed. Scanning for next opportunity."

**MACD Add-on Check** (for bots where `has_macd_confirmed == false`):

Run MACD divergence check (Step 3C) again for this instId.
If MACD divergence now confirmed AND `oi_pct_change >= 10%`:
- Stop current bot, recreate with next position size tier (max 100 USDT total)
- Set `has_macd_confirmed = true`

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
├─ 4. PHASE 3: Grid Strategy
│   ├─ Scan top-5 gainers
│   ├─ Check divergence on candidates
│   ├─ Check OI + MACD for sizing
│   ├─ Create new grid bots (if budget available)
│   └─ Manage existing bots (SL / TP / add-on)
│
└─ 5. Save state.json
```

---

## Edge Cases

- **BTC liquidation risk**: At 50x isolated, liquidation occurs ~2% adverse move. SL at -1.2% exits before liquidation. If SL order fails to fill (gap down), force market close on next cycle if price < avg_entry * 0.975.
- **Insufficient balance**: If `free_usdt < 200`, skip new BTC entry. If `free_usdt < 20`, skip new grid bots.
- **Grid creation fails**: Log error, try next token in top-5 list.
- **Token suspended**: Skip token, move to next candidate.
- **TP partial close — bot recreation fails**: Retry once. If still fails, stop bot entirely and log.
- **Multiple divergence signals same token**: Use the most recent confirmed divergence only.
- **state.json missing**: Initialize with default empty state and proceed.
