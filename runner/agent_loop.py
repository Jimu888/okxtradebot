#!/usr/bin/env python3
"""
OKX Compound Strategy — Python + Claude Architecture

Python layer:  data fetching, indicator parsing, divergence detection,
               SL/TP checks, state management
Claude layer:  receives a structured summary, outputs JSON trade decisions
"""

import json
import os
import re
import subprocess
import time
import logging
from pathlib import Path
from datetime import datetime, timezone

import anthropic
from dotenv import load_dotenv

load_dotenv()

# ── Config ────────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
OKX_PROFILE       = os.getenv("OKX_PROFILE", "live")
LOOP_INTERVAL     = int(os.getenv("LOOP_INTERVAL_SECONDS", "300"))  # 5 min
MODEL             = os.getenv("CLAUDE_MODEL", "claude-haiku-4-5-20251001")

BASE_DIR   = Path(__file__).parent.parent
STATE_FILE = BASE_DIR / "runner" / "state.json"
LOG_FILE   = BASE_DIR / "runner" / "agent.log"

# Strategy constants
BTC_TOTAL_MARGIN   = 400      # USDT
BTC_LEVERAGE       = 50
BTC_CT_VAL         = 0.01     # BTC per contract
BTC_SL_PCT         = 0.012    # 1.2%
BTC_RSI_OVERSOLD   = 30
BTC_CCI_OVERSOLD   = -100
BTC_RSI_OVERBOUGHT = 70
BTC_CCI_OVERBOUGHT = 100
BTC_DIF_ZERO_THRESHOLD = 50   # abs(DIF) < 50 counts as zero

GRID_TOTAL_BUDGET  = 100      # USDT
GRID_LEVERAGE      = 10
GRID_NUM           = 10
GRID_ATR_MULT      = 1.5
GRID_MAX_BOTS      = 2
GRID_OI_THRESHOLD  = 0.10     # 10%
DIVERGENCE_CANDLES = 20       # look-back window

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)

# ── State ─────────────────────────────────────────────────────────────────────
DEFAULT_STATE = {
    "btc_activated": False,
    "btc_position": {
        "active": False,
        "entry_count": 0,
        "avg_entry_price": 0.0,
        "total_sz": 0,
        "remaining_pct": 100,
    },
    "grid_bots": [],
}

def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception as e:
            log.warning(f"state.json load failed: {e}. Using default.")
    return json.loads(json.dumps(DEFAULT_STATE))

def save_state(state: dict):
    STATE_FILE.write_text(json.dumps(state, indent=2))
    log.debug("State saved.")

# ── OKX CLI helpers ───────────────────────────────────────────────────────────
def okx(cmd: str, require_auth: bool = False) -> str:
    if require_auth and "--profile" not in cmd:
        cmd = f"{cmd} --profile {OKX_PROFILE}"
    log.debug(f"[CLI] {cmd}")
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
        out = r.stdout.strip()
        err = r.stderr.strip()
        if r.returncode != 0:
            log.warning(f"[CLI ERR] {err or out}")
            return ""
        return out
    except subprocess.TimeoutExpired:
        log.error(f"[CLI TIMEOUT] {cmd}")
        return ""

def okx_json(cmd: str, require_auth: bool = False) -> dict | list | None:
    out = okx(cmd + " --json", require_auth)
    if not out:
        return None
    try:
        return json.loads(out)
    except Exception:
        # Try to extract JSON from mixed output
        m = re.search(r'(\{.*\}|\[.*\])', out, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1))
            except Exception:
                pass
        log.warning(f"[CLI] Could not parse JSON: {out[:200]}")
        return None

def parse_float(text: str) -> float | None:
    """Extract first float from a string."""
    m = re.search(r'-?\d+\.?\d*', text.replace(',', ''))
    return float(m.group()) if m else None

# ── Market data ───────────────────────────────────────────────────────────────
def get_price(inst_id: str) -> float | None:
    data = okx_json(f"okx market ticker {inst_id}")
    if isinstance(data, dict):
        return float(data.get("last") or data.get("price") or 0) or None
    if isinstance(data, list) and data:
        return float(data[0].get("last") or 0) or None
    raw = okx(f"okx market ticker {inst_id}")
    return parse_float(raw)

def get_indicator(name: str, inst_id: str, period: int | None, bar: str, limit: int = 1) -> list[float]:
    """Return list of most-recent indicator values (index 0 = latest)."""
    cmd = f"okx market indicator {name} {inst_id} --bar {bar} --limit {limit}"
    if period:
        cmd += f" --period {period}"
    data = okx_json(cmd)
    if isinstance(data, list):
        vals = []
        for item in data:
            v = item.get("value") or item.get(name.lower()) or item.get("v")
            if v is not None:
                try:
                    vals.append(float(v))
                except Exception:
                    pass
        if vals:
            return vals
    raw = okx(cmd)
    lines = [l.strip() for l in raw.splitlines() if l.strip()]
    result = []
    for line in lines:
        v = parse_float(line)
        if v is not None:
            result.append(v)
    return result

def get_candles(inst_id: str, bar: str, limit: int) -> list[dict]:
    """Return OHLCV candles newest-first."""
    data = okx_json(f"okx market candles {inst_id} --bar {bar} --limit {limit}")
    if isinstance(data, list):
        result = []
        for c in data:
            if isinstance(c, list) and len(c) >= 5:
                result.append({
                    "ts": int(c[0]), "o": float(c[1]), "h": float(c[2]),
                    "l": float(c[3]), "c": float(c[4])
                })
            elif isinstance(c, dict):
                result.append({
                    "ts": int(c.get("ts", 0)),
                    "o": float(c.get("o", 0)), "h": float(c.get("h", 0)),
                    "l": float(c.get("l", 0)), "c": float(c.get("c", 0))
                })
        return result
    return []

def get_top_gainers(n: int = 5) -> list[str]:
    """Return top N SWAP instIds sorted by 24h change descending."""
    data = okx_json("okx market tickers SWAP")
    if not isinstance(data, list):
        return []
    items = []
    for t in data:
        try:
            change = float(t.get("change24h") or t.get("changeUtc0") or 0)
            inst = t.get("instId", "")
            if inst.endswith("-USDT-SWAP") and change > 0:
                items.append((inst, change))
        except Exception:
            pass
    items.sort(key=lambda x: x[1], reverse=True)
    return [inst for inst, _ in items[:n]]

def get_oi(inst_id: str) -> float | None:
    data = okx_json(f"okx market open-interest --instType SWAP --instId {inst_id}")
    if isinstance(data, list) and data:
        v = data[0].get("oi") or data[0].get("oiCcy")
        return float(v) if v else None
    if isinstance(data, dict):
        v = data.get("oi") or data.get("oiCcy")
        return float(v) if v else None
    return None

def get_macd(inst_id: str, bar: str, limit: int = 20) -> list[dict]:
    """Return MACD data: list of {dif, dea, macd} newest-first."""
    data = okx_json(f"okx market indicator MACD {inst_id} --bar {bar} --limit {limit}")
    if isinstance(data, list):
        result = []
        for item in data:
            if isinstance(item, dict):
                dif = item.get("dif") or item.get("DIF") or item.get("fast")
                dea = item.get("dea") or item.get("DEA") or item.get("slow")
                if dif is not None:
                    result.append({"dif": float(dif), "dea": float(dea or 0)})
        if result:
            return result
    return []

# ── Divergence detection ──────────────────────────────────────────────────────
def find_swing_lows(candles: list[dict], window: int = 2) -> list[int]:
    """Return indices of swing lows (local minima)."""
    lows = []
    for i in range(window, len(candles) - window):
        if all(candles[i]["l"] < candles[i - j]["l"] for j in range(1, window + 1)) and \
           all(candles[i]["l"] < candles[i + j]["l"] for j in range(1, window + 1)):
            lows.append(i)
    return lows

def find_swing_highs(candles: list[dict], window: int = 2) -> list[int]:
    """Return indices of swing highs (local maxima)."""
    highs = []
    for i in range(window, len(candles) - window):
        if all(candles[i]["h"] > candles[i - j]["h"] for j in range(1, window + 1)) and \
           all(candles[i]["h"] > candles[i + j]["h"] for j in range(1, window + 1)):
            highs.append(i)
    return highs

def detect_rsi_divergence(inst_id: str) -> dict | None:
    """
    Returns divergence info or None.
    Uses candles (newest = index 0) and RSI values aligned by index.
    """
    candles = get_candles(inst_id, "5m", DIVERGENCE_CANDLES)
    rsi_vals = get_indicator("RSI", inst_id, 14, "5m", DIVERGENCE_CANDLES)
    if len(candles) < DIVERGENCE_CANDLES or len(rsi_vals) < DIVERGENCE_CANDLES:
        return None

    # Reverse so index 0 = oldest (easier swing logic)
    candles_asc = list(reversed(candles))
    rsi_asc = list(reversed(rsi_vals))

    swing_lows = find_swing_lows(candles_asc)
    swing_highs = find_swing_highs(candles_asc)

    # Bullish divergence: price lower low, RSI higher low
    if len(swing_lows) >= 2:
        i1, i2 = swing_lows[-2], swing_lows[-1]  # i2 is more recent
        price_lower = candles_asc[i2]["l"] < candles_asc[i1]["l"]
        rsi_higher = rsi_asc[i2] > rsi_asc[i1]
        if price_lower and rsi_higher:
            return {
                "type": "bullish",
                "divergence_low": candles_asc[i2]["l"],
                "divergence_high": max(c["h"] for c in candles_asc),
                "rsi_at_low": rsi_asc[i2],
            }

    # Bearish divergence: price higher high, RSI lower high
    if len(swing_highs) >= 2:
        i1, i2 = swing_highs[-2], swing_highs[-1]
        price_higher = candles_asc[i2]["h"] > candles_asc[i1]["h"]
        rsi_lower = rsi_asc[i2] < rsi_asc[i1]
        if price_higher and rsi_lower:
            return {
                "type": "bearish",
                "divergence_high": candles_asc[i2]["h"],
                "divergence_low": min(c["l"] for c in candles_asc),
                "rsi_at_high": rsi_asc[i2],
            }

    return None

def detect_macd_divergence(inst_id: str, div_type: str) -> bool:
    """
    Check MACD divergence to confirm RSI divergence.
    div_type: 'bullish' or 'bearish'
    Looks for two crossover points and compares DIF values.
    """
    macd_data = get_macd(inst_id, "5m", DIVERGENCE_CANDLES)
    candles = get_candles(inst_id, "5m", DIVERGENCE_CANDLES)
    if len(macd_data) < 4 or len(candles) < DIVERGENCE_CANDLES:
        return False

    macd_asc = list(reversed(macd_data))
    candles_asc = list(reversed(candles))

    # Find crossover points (where DIF crosses DEA)
    crossovers = []
    for i in range(1, len(macd_asc)):
        prev = macd_asc[i - 1]
        curr = macd_asc[i]
        if prev["dif"] < prev["dea"] and curr["dif"] >= curr["dea"]:
            crossovers.append({"idx": i, "type": "golden", "dif": curr["dif"],
                                "price": candles_asc[i]["c"] if i < len(candles_asc) else 0})
        elif prev["dif"] > prev["dea"] and curr["dif"] <= curr["dea"]:
            crossovers.append({"idx": i, "type": "death", "dif": curr["dif"],
                                "price": candles_asc[i]["c"] if i < len(candles_asc) else 0})

    if len(crossovers) < 2:
        return False

    c1, c2 = crossovers[-2], crossovers[-1]

    if div_type == "bullish":
        # Bearish: price new low, MACD crossover DIF value higher (less negative)
        price_lower_low = c2["price"] < c1["price"]
        macd_higher = c2["dif"] > c1["dif"]
        return price_lower_low and macd_higher

    if div_type == "bearish":
        # Bullish: price new high, MACD crossover DIF value lower
        price_higher_high = c2["price"] > c1["price"]
        macd_lower = c2["dif"] < c1["dif"]
        return price_higher_high and macd_lower

    return False

# ── Position sizing ───────────────────────────────────────────────────────────
def calc_grid_position_size(has_rsi: bool, has_macd: bool, oi_increase_pct: float,
                             budget_remaining: float) -> int:
    if not has_rsi:
        return 0
    if has_macd and oi_increase_pct >= GRID_OI_THRESHOLD * 100:
        sz = 100
    elif has_macd:
        sz = 40
    elif oi_increase_pct >= GRID_OI_THRESHOLD * 100:
        sz = 30
    else:
        sz = 20
    return int(min(sz, budget_remaining))

def calc_btc_sz(margin_usdt: float, price: float) -> int:
    notional = margin_usdt * BTC_LEVERAGE
    sz = int(notional / (price * BTC_CT_VAL))
    return max(sz, 1)

# ── Data gathering phase ──────────────────────────────────────────────────────
def gather_btc_data(state: dict) -> dict:
    result = {"activated": state["btc_activated"]}

    # Check activation
    if not state["btc_activated"]:
        macd = get_macd("BTC-USDT-SWAP", "1H", 3)
        if macd:
            dif = macd[0]["dif"]
            result["dif_1h"] = dif
            result["activation_met"] = abs(dif) <= BTC_DIF_ZERO_THRESHOLD
        else:
            result["activation_met"] = False
        if not result["activation_met"]:
            result["skip_reason"] = f"1H DIF={result.get('dif_1h', 'N/A')}, waiting for zero cross"
            return result

    # Get 5m indicators
    price = get_price("BTC-USDT-SWAP")
    rsi_vals = get_indicator("RSI", "BTC-USDT-SWAP", 14, "5m", 1)
    cci_vals = get_indicator("CCI", "BTC-USDT-SWAP", 20, "5m", 1)

    result["price"]   = price
    result["rsi_5m"]  = rsi_vals[0] if rsi_vals else None
    result["cci_5m"]  = cci_vals[0] if cci_vals else None
    result["oversold"] = (
        result["rsi_5m"] is not None and result["cci_5m"] is not None and
        result["rsi_5m"] < BTC_RSI_OVERSOLD and
        result["cci_5m"] < BTC_CCI_OVERSOLD
    )

    pos = state["btc_position"]
    if pos["active"]:
        avg = pos["avg_entry_price"]
        result["sl_price"] = round(avg * (1 - BTC_SL_PCT), 2)
        result["sl_triggered"]  = price <= result["sl_price"] if price else False
        result["tp1_triggered"] = (result["cci_5m"] or 0) > BTC_CCI_OVERBOUGHT
        result["tp2_triggered"] = (result["rsi_5m"] or 0) > BTC_RSI_OVERBOUGHT

    return result

def gather_grid_data(state: dict) -> dict:
    result = {"candidates": [], "active_bots_status": []}

    # Check existing bots
    for bot in state["grid_bots"]:
        price = get_price(bot["instId"])
        bot_detail = okx_json(f"okx bot grid details --algoId {bot['algoId']}", require_auth=True)
        pnl_pct = 0.0
        if isinstance(bot_detail, dict):
            pnl = bot_detail.get("pnlRatio") or bot_detail.get("profit")
            if pnl:
                try:
                    pnl_pct = float(pnl) * 100
                except Exception:
                    pass
        result["active_bots_status"].append({
            "algoId": bot["algoId"],
            "instId": bot["instId"],
            "direction": bot["direction"],
            "current_price": price,
            "stop_loss_px": bot["stop_loss_px"],
            "pnl_pct": pnl_pct,
            "initial_sz": bot["initial_sz"],
            "current_sz": bot["current_sz"],
            "has_macd_confirmed": bot.get("has_macd_confirmed", False),
            "entry_oi": bot.get("entry_oi", 0),
            "sl_triggered": (
                (bot["direction"] == "long" and price and price < bot["stop_loss_px"]) or
                (bot["direction"] == "short" and price and price > bot["stop_loss_px"])
            ),
        })

    # Budget remaining
    grid_used = sum(b["current_sz"] for b in state["grid_bots"])
    budget_remaining = GRID_TOTAL_BUDGET - grid_used
    result["budget_remaining"] = budget_remaining

    if budget_remaining < 20 or len(state["grid_bots"]) >= GRID_MAX_BOTS:
        return result

    # Scan top gainers
    active_insts = {b["instId"] for b in state["grid_bots"]}
    top5 = [t for t in get_top_gainers(5) if t not in active_insts]

    for inst_id in top5:
        div = detect_rsi_divergence(inst_id)
        if not div:
            continue

        has_macd = detect_macd_divergence(inst_id, div["type"])

        # OI comparison
        current_oi = get_oi(inst_id)
        oi_increase_pct = 0.0
        if current_oi:
            # Use current OI as baseline if no prior reference
            oi_increase_pct = 0.0  # Will be set by Claude if MACD just fired

        sz = calc_grid_position_size(
            has_rsi=True,
            has_macd=has_macd,
            oi_increase_pct=oi_increase_pct,
            budget_remaining=budget_remaining,
        )
        if sz <= 0:
            continue

        # ATR for grid range
        atr_vals = get_indicator("ATR", inst_id, 14, "5m", 1)
        atr = atr_vals[0] if atr_vals else None
        price = get_price(inst_id)

        grid_min = grid_max = None
        if atr and price:
            grid_min = round(price - GRID_ATR_MULT * atr, 8)
            grid_max = round(price + GRID_ATR_MULT * atr, 8)

        result["candidates"].append({
            "instId": inst_id,
            "divergence_type": div["type"],
            "divergence_low": div.get("divergence_low"),
            "divergence_high": div.get("divergence_high"),
            "has_rsi_divergence": True,
            "has_macd_divergence": has_macd,
            "current_oi": current_oi,
            "oi_increase_pct": oi_increase_pct,
            "proposed_sz": sz,
            "price": price,
            "atr": atr,
            "grid_min": grid_min,
            "grid_max": grid_max,
            "stop_loss_px": div.get("divergence_low") if div["type"] == "long" else div.get("divergence_high"),
        })

        # If one token takes full budget, stop scanning
        if sz >= GRID_TOTAL_BUDGET:
            break

    return result

def gather_account_data() -> dict:
    balance = okx_json("okx account balance", require_auth=True)
    positions = okx_json("okx account positions", require_auth=True)
    free_usdt = 0.0
    if isinstance(balance, list):
        for item in balance:
            if item.get("ccy") == "USDT":
                free_usdt = float(item.get("availBal") or item.get("availEq") or 0)
    elif isinstance(balance, dict):
        free_usdt = float(balance.get("availBal") or balance.get("availEq") or 0)
    return {
        "free_usdt": free_usdt,
        "positions": positions if isinstance(positions, list) else [],
    }

# ── Build summary for Claude ──────────────────────────────────────────────────
def build_summary(account: dict, btc: dict, grid: dict, state: dict) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [f"=== STRATEGY CYCLE {now} ===", ""]

    lines.append(f"ACCOUNT: free_usdt={account['free_usdt']:.2f}")
    lines.append("")

    # BTC
    lines.append("── BTC STRATEGY (400 USDT budget, 50x isolated) ──")
    if not btc.get("activated") and not btc.get("activation_met"):
        lines.append(f"STATUS: NOT ACTIVATED — {btc.get('skip_reason', '')}")
    else:
        if btc.get("activation_met") and not btc.get("activated"):
            lines.append("STATUS: ACTIVATION CONDITION MET (1H DIF near zero) → set btc_activated=true")
        else:
            lines.append("STATUS: ACTIVATED")

        pos = state["btc_position"]
        if pos["active"]:
            lines.append(f"POSITION: {pos['entry_count']} entries, avg={pos['avg_entry_price']}, "
                         f"sz={pos['total_sz']}, remaining={pos['remaining_pct']}%")
            lines.append(f"  SL price: {btc.get('sl_price')} | triggered: {btc.get('sl_triggered')}")
            lines.append(f"  RSI={btc.get('rsi_5m'):.1f} | CCI={btc.get('cci_5m'):.1f}")
            lines.append(f"  TP1(CCI>100): {btc.get('tp1_triggered')} | TP2(RSI>70): {btc.get('tp2_triggered')}")
        else:
            lines.append("POSITION: none")
            lines.append(f"  RSI={btc.get('rsi_5m'):.1f} | CCI={btc.get('cci_5m'):.1f} | "
                         f"price={btc.get('price')}")
            lines.append(f"  OVERSOLD signal: {btc.get('oversold')}")
            if btc.get("oversold") and pos["entry_count"] == 0:
                sz = calc_btc_sz(BTC_TOTAL_MARGIN / 2, btc["price"]) if btc.get("price") else "?"
                lines.append(f"  → ENTRY 1 opportunity: sz={sz} contracts (200 USDT margin)")
            elif btc.get("oversold") and pos["entry_count"] == 1:
                sz = calc_btc_sz(BTC_TOTAL_MARGIN / 2, btc["price"]) if btc.get("price") else "?"
                lines.append(f"  → ENTRY 2 opportunity: sz={sz} contracts (200 USDT margin)")
    lines.append("")

    # Grid
    lines.append("── GRID STRATEGY (100 USDT budget, 10x isolated) ──")
    lines.append(f"Budget remaining: {grid['budget_remaining']} USDT | Active bots: {len(state['grid_bots'])}")

    for bot in grid["active_bots_status"]:
        sl_flag = " ← SL TRIGGERED" if bot["sl_triggered"] else ""
        tp_flag = ""
        if bot["pnl_pct"] >= 200 and bot["current_sz"] <= bot["initial_sz"] * 0.26:
            tp_flag = " ← TP3 (close all)"
        elif bot["pnl_pct"] >= 100 and bot["current_sz"] <= bot["initial_sz"] * 0.51:
            tp_flag = " ← TP2 (reduce to 25%)"
        elif bot["pnl_pct"] >= 60 and bot["current_sz"] == bot["initial_sz"]:
            tp_flag = " ← TP1 (reduce to 50%)"
        lines.append(f"  BOT {bot['algoId']}: {bot['instId']} {bot['direction']} "
                     f"sz={bot['current_sz']} pnl={bot['pnl_pct']:.1f}%"
                     f" price={bot['current_price']} sl={bot['stop_loss_px']}{sl_flag}{tp_flag}")

    if grid["candidates"]:
        lines.append("New candidates:")
        for c in grid["candidates"]:
            lines.append(f"  {c['instId']}: {c['divergence_type']} divergence | "
                         f"RSI={c['has_rsi_divergence']} MACD={c['has_macd_divergence']} "
                         f"OI+={c['oi_increase_pct']:.1f}% | proposed_sz={c['proposed_sz']} USDT | "
                         f"grid={c['grid_min']}-{c['grid_max']} atr={c['atr']} | "
                         f"sl={c['stop_loss_px']}")
    else:
        lines.append("No new candidates.")

    lines.append("")
    lines.append(f"CURRENT STATE:\n{json.dumps(state, indent=2)}")
    return "\n".join(lines)

# ── Claude decision ───────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are the decision engine for an OKX crypto trading strategy.
Python has already computed all indicators and signals. Your job:
1. Review the cycle summary
2. Decide which actions to take
3. Return ONLY a JSON array of actions — no explanation text

Action schema:
{"action": "<type>", ...params}

Action types:
- {"action": "activate_btc"}
- {"action": "btc_entry", "sz": <int>, "price": <float>}
- {"action": "btc_sl_close", "sz": <int>}
- {"action": "btc_tp1_close", "sz": <int>}
- {"action": "btc_tp2_close", "sz": <int>}
- {"action": "grid_create", "instId": "<str>", "direction": "long|short",
   "minPx": <float>, "maxPx": <float>, "sz": <int>,
   "stop_loss_px": <float>, "entry_oi": <float>,
   "has_macd_confirmed": <bool>}
- {"action": "grid_stop", "algoId": "<str>", "instId": "<str>", "reason": "sl|tp1|tp2|tp3"}
- {"action": "grid_reduce", "algoId": "<str>", "instId": "<str>",
   "new_sz": <int>, "reason": "tp1|tp2"}
- {"action": "noop", "reason": "<str>"}

Rules:
- Always include SL closes when sl_triggered=true
- For TP, close in order: tp1 before tp2 (unless RSI>70 directly, then skip to tp2)
- For grid TP partial: stop bot + recreate with new_sz (handled by executor)
- Return [] if truly nothing to do, but prefer noop with reason
- Return valid JSON only, no markdown code blocks"""

def ask_claude(client: anthropic.Anthropic, summary: str) -> list[dict]:
    response = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": summary}],
    )
    text = response.content[0].text.strip()
    # Strip markdown fences if present
    text = re.sub(r"^```[a-z]*\n?", "", text)
    text = re.sub(r"\n?```$", "", text)
    try:
        actions = json.loads(text)
        if isinstance(actions, dict):
            actions = [actions]
        return actions
    except Exception as e:
        log.error(f"Claude output parse failed: {e}\nRaw: {text[:500]}")
        return [{"action": "noop", "reason": "claude parse error"}]

# ── Action executor ───────────────────────────────────────────────────────────
def execute_actions(actions: list[dict], state: dict, btc_data: dict, grid_data: dict) -> dict:
    for act in actions:
        a = act.get("action")
        log.info(f"[ACTION] {json.dumps(act)}")

        if a == "noop":
            log.info(f"  → No-op: {act.get('reason')}")

        elif a == "activate_btc":
            state["btc_activated"] = True
            log.info("  → BTC strategy activated")

        elif a == "btc_entry":
            sz = act["sz"]
            price = act["price"]
            okx(f"okx swap set-leverage --instId BTC-USDT-SWAP --lever {BTC_LEVERAGE} "
                f"--mgnMode isolated", require_auth=True)
            result = okx(f"okx swap place --instId BTC-USDT-SWAP --side buy "
                         f"--ordType market --sz {sz} --posSide long "
                         f"--tdMode isolated", require_auth=True)
            log.info(f"  → BTC entry: {result}")
            pos = state["btc_position"]
            if pos["active"]:
                # Second entry — recalculate average
                old_sz = pos["total_sz"]
                new_sz = old_sz + sz
                pos["avg_entry_price"] = round(
                    (pos["avg_entry_price"] * old_sz + price * sz) / new_sz, 2)
                pos["total_sz"] = new_sz
                pos["entry_count"] = 2
            else:
                pos["active"] = True
                pos["entry_count"] = 1
                pos["avg_entry_price"] = price
                pos["total_sz"] = sz
                pos["remaining_pct"] = 100

        elif a == "btc_sl_close":
            sz = act["sz"]
            result = okx(f"okx swap place --instId BTC-USDT-SWAP --side sell "
                         f"--ordType market --sz {sz} --posSide long "
                         f"--tdMode isolated --reduceOnly", require_auth=True)
            log.info(f"  → BTC SL close: {result}")
            state["btc_position"] = {**DEFAULT_STATE["btc_position"]}

        elif a == "btc_tp1_close":
            sz = act["sz"]
            result = okx(f"okx swap place --instId BTC-USDT-SWAP --side sell "
                         f"--ordType market --sz {sz} --posSide long "
                         f"--tdMode isolated --reduceOnly", require_auth=True)
            log.info(f"  → BTC TP1 close 20%: {result}")
            state["btc_position"]["remaining_pct"] = 80

        elif a == "btc_tp2_close":
            sz = act["sz"]
            result = okx(f"okx swap place --instId BTC-USDT-SWAP --side sell "
                         f"--ordType market --sz {sz} --posSide long "
                         f"--tdMode isolated --reduceOnly", require_auth=True)
            log.info(f"  → BTC TP2 close all remaining: {result}")
            state["btc_position"] = {**DEFAULT_STATE["btc_position"]}

        elif a == "grid_create":
            inst = act["instId"]
            okx(f"okx swap set-leverage --instId {inst} --lever {GRID_LEVERAGE} "
                f"--mgnMode isolated", require_auth=True)
            result = okx(f"okx bot grid create --instId {inst} "
                         f"--algoOrdType contract_grid "
                         f"--minPx {act['minPx']} --maxPx {act['maxPx']} "
                         f"--gridNum {GRID_NUM} --direction {act['direction']} "
                         f"--lever {GRID_LEVERAGE} --sz {act['sz']}", require_auth=True)
            log.info(f"  → Grid created: {result}")
            # Extract algoId from result
            algo_id = ""
            m = re.search(r'"algoId"\s*:\s*"([^"]+)"', result)
            if m:
                algo_id = m.group(1)
            if algo_id:
                state["grid_bots"].append({
                    "algoId": algo_id,
                    "instId": inst,
                    "direction": act["direction"],
                    "entry_oi": act.get("entry_oi", 0),
                    "initial_sz": act["sz"],
                    "current_sz": act["sz"],
                    "stop_loss_px": act["stop_loss_px"],
                    "has_macd_confirmed": act.get("has_macd_confirmed", False),
                })

        elif a == "grid_stop":
            algo_id = act["algoId"]
            inst = act["instId"]
            result = okx(f"okx bot grid stop --algoId {algo_id}", require_auth=True)
            log.info(f"  → Grid stopped ({act.get('reason')}): {result}")
            state["grid_bots"] = [b for b in state["grid_bots"] if b["algoId"] != algo_id]

        elif a == "grid_reduce":
            # Stop and recreate with smaller size
            algo_id = act["algoId"]
            inst = act["instId"]
            new_sz = act["new_sz"]
            bot = next((b for b in state["grid_bots"] if b["algoId"] == algo_id), None)
            if not bot:
                continue
            # Stop old bot
            okx(f"okx bot grid stop --algoId {algo_id}", require_auth=True)
            # Get fresh ATR and price for new grid
            price = get_price(inst)
            atr_vals = get_indicator("ATR", inst, 14, "5m", 1)
            atr = atr_vals[0] if atr_vals else None
            if price and atr:
                grid_min = round(price - GRID_ATR_MULT * atr, 8)
                grid_max = round(price + GRID_ATR_MULT * atr, 8)
                result = okx(f"okx bot grid create --instId {inst} "
                             f"--algoOrdType contract_grid "
                             f"--minPx {grid_min} --maxPx {grid_max} "
                             f"--gridNum {GRID_NUM} --direction {bot['direction']} "
                             f"--lever {GRID_LEVERAGE} --sz {new_sz}", require_auth=True)
                log.info(f"  → Grid recreated with sz={new_sz}: {result}")
                m = re.search(r'"algoId"\s*:\s*"([^"]+)"', result)
                new_algo_id = m.group(1) if m else ""
                # Update state
                state["grid_bots"] = [b for b in state["grid_bots"] if b["algoId"] != algo_id]
                if new_algo_id:
                    bot["algoId"] = new_algo_id
                    bot["current_sz"] = new_sz
                    state["grid_bots"].append(bot)

    return state

# ── Main cycle ────────────────────────────────────────────────────────────────
def run_cycle(client: anthropic.Anthropic):
    state = load_state()
    log.info("━━━ Cycle start ━━━")

    # 1. Gather data
    account = gather_account_data()
    btc     = gather_btc_data(state)
    grid    = gather_grid_data(state)

    # 2. Build summary and ask Claude
    summary = build_summary(account, btc, grid, state)
    log.debug(f"[SUMMARY]\n{summary}")

    actions = ask_claude(client, summary)
    log.info(f"[CLAUDE] Decided {len(actions)} actions: {[a.get('action') for a in actions]}")

    # 3. Execute actions
    state = execute_actions(actions, state, btc, grid)

    # 4. Save state
    save_state(state)
    log.info("━━━ Cycle end ━━━\n")

# ── Entry point ───────────────────────────────────────────────────────────────
def main():
    if not ANTHROPIC_API_KEY:
        raise ValueError("ANTHROPIC_API_KEY not set in .env")

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    log.info(f"Starting OKX Compound Strategy | model={MODEL} | interval={LOOP_INTERVAL}s")

    while True:
        try:
            run_cycle(client)
        except KeyboardInterrupt:
            log.info("Stopped by user.")
            break
        except Exception as e:
            log.error(f"Cycle error: {e}", exc_info=True)

        log.info(f"Next cycle in {LOOP_INTERVAL}s...")
        time.sleep(LOOP_INTERVAL)

if __name__ == "__main__":
    main()
