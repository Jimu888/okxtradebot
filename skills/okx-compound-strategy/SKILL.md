---
name: okx-compound-strategy
description: >
  AI-driven compound trading strategy v3.6.0 with Price Action + MACD convergence.
  Phase 0.5: market context (Supertrend, ADX, BBWidth, HV, MFI, funding, L/S ratio, sentiment).
  Phase 0.6: Gemma4:e4b macro analysis (Daily/12H/4H/1H trends, S&R levels, DIRECTION).
  BTC-USDT-SWAP: 50x isolated, bidirectional (LONG/SHORT/FLAT per Gemma4).
  Entry: 8-dimension 100-pt scoring + Pinbar auto-detection + hot-spot confluence bonus.
  Exit: dynamic TP thresholds (BULLISH/NEUTRAL/BEARISH) + MACD 30m divergence TP
        + overextension mean-reversion TP + support-break SL.
  RAVE-USDT-SWAP: short with 6-signal detection incl. MACD head-and-shoulders top.
  Grid: dual-scan (gainers + OI), 7-dimension scoring, funding-rate avoidance.
  Self-iteration authorized within defined limits. All orders tagged agentTradeKit.
license: MIT
metadata:
  author: compound-strategy
  version: "3.6.0"
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
  "peak_equity": 0,
  "btc_activated": false,
  "gemma4_analysis": {
    "trend_daily": "",
    "trend_12h": "",
    "trend_4h": "",
    "trend_1h": "",
    "support_1": 0,
    "support_2": 0,
    "resistance_1": 0,
    "resistance_2": 0,
    "direction": "",
    "confidence": "",
    "updated_at": ""
  },
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

## PHASE 0.1 — AI综合决策层 (v3.14, 比赛合规核心)

**此策略由Claude (AI) 作为核心决策者运行**, 规则评分只是AI的**输入参考**, **最终决定永远由AI做出**, 可override任何机械规则。

### AI决策原则
每个开仓/平仓决策, AI必须:
1. 收集所有输入信号 (评分/结构/context)
2. 综合考虑 (不是简单加权平均)
3. 输出binding decision + rationale
4. 允许override机械规则 (记录为什么)

### Binding Decision格式
```
[AI DECISION {instId} {timestamp}]
Input signals:
  - MTF Confluence score: {n}/100
  - Macro context: {state}
  - Structure: {description}
  - Volatility regime: {regime}
  
Mechanical rule says: {GO/SKIP/HOLD}
AI synthesis:
  {3-5 sentences reasoning, integrating quantitative + qualitative}
Final decision: {action}
Override mechanical?: {yes/no and why}
Position params:
  size: {margin}
  leverage: {x}
  SL: {price, based on structure}
  TP: {price, based on structure}
Risk: {worst case loss}
Confidence: {0-1}
```

### AI override scenarios
- 评分65分但结构破位 → override to SKIP
- 评分40分但多时间框架一致 → override to GO (small size)
- TP规则说平仓但momentum仍强 → override to HOLD
- SL规则触发但price action示反转 → override to HOLD 1 more bar

---

## PHASE 0.2 — Macro Bear Filter (v3.14, grid protection)

**来源**: 今日EDGE/THETA grid在单边下跌市死扛导致-$20损失

### 规则
每cycle必须check:
```python
btc_1h_supertrend = get_supertrend("BTC", "1H")
btc_30m_last3 = last_3_30m_bars  # close < open count

macro_bearish = (
    btc_1h_supertrend == "DOWN" AND
    sum(b.close < b.open for b in btc_30m_last3) >= 2
)
```

### Grid响应 (若macro_bearish):
| 当前grid状态 | 行动 |
|---|---|
| 新grid创建请求 | **拒绝** (等macro转好) |
| 已运行grid pnl > 0% | 保持 + trail 30% drawdown |
| 已运行grid pnl -5%~0% | 警戒 + tighten trail |
| 已运行grid pnl < -5% | **立即stop** (不等-10%) |

### 解除条件
`BTC 1H Supertrend UP持续2小时` AND `30m连续2根阳线` → 恢复正常grid逻辑

---

## PHASE 0.3 — Leverage Pre-Check (v3.14, 强制)

**来源**: BTC杠杆错误3次 (10x vs 设计50x)

### 每次place新仓前必须run:
```bash
actual_lever=$(okx swap get-leverage --instId ${INST_ID} --mgnMode isolated | grep short | awk '{print $4}')

if [ "$actual_lever" != "$EXPECTED_LEVER" ]; then
  okx swap leverage --instId ${INST_ID} --lever ${EXPECTED_LEVER} --mgnMode isolated --posSide short
  # re-verify
  verify_lever
fi

log "LEVERAGE CHECK: ${INST_ID} lever=${EXPECTED_LEVER} ✓"
```

### 各标的默认
- BTC = **50x** (永远)
- ETH = **50x**
- RAVE = **5-10x** (高波动, 不用50x)
- Altcoins动态扫描 = **5x**
- Grid = **10x**

---

## PHASE 0.4 — 动态单边趋势标的扫描（v3.8, 每 cycle 必跑）

**改造原因 (v3.7 → v3.8)**:
v3.7 仅用 24h 涨跌幅 + 24h 位置筛选，但"24h跌很多"不等于"现在还在单边下跌"。
很多币24h跌20%但最近2小时已经筑底反弹。这种"尸体"挂空单=送钱。
v3.8 增加**多指标趋势确认**，只选择真正处于单边趋势中的标的。

### 第一步：初筛 (基于24h数据 + 成交额)
```
粗筛门槛:
  vol > 50M USDT  (流动性保障)
  AND (24h跌幅>12% 或 24h涨幅>10%)  (放宽阈值, 因有后续趋势filter)
```
输出初筛候选池（预计每cycle 5-20个标的）。

### 第二步：趋势确认栈 (对每个初筛候选, 并行拉取指标)
需要拉取的指标：
- **1H 均线**: price / EMA20 / EMA50 (对齐判断)
- **1H Supertrend**: direction (UP/DOWN)
- **1H ADX + DI+/DI-**: 趋势强度与方向动能
- **5m 最近5根K线 close**: 短线动量一致性

### 第三步：质量分级 (对每个候选)

**SHORT 质量等级**:

| 等级 | 条件 (需全部满足) | 执行动作 |
|------|------------------|----------|
| **A级 满仓** | 1) 1H price < EMA20 < EMA50 (均线空头排列)<br>2) 1H Supertrend = DOWN<br>3) 1H ADX > 25 (强趋势)<br>4) 1H DI- > DI+ (空方动能强)<br>5) 5m最近5根 ≥4根阴线 | **市价SHORT** (40U margin 5x)<br>OCO: TP -15% / SL +8% |
| **B级 限价** | 满足A级中4项 | 限价SHORT @ 当前×1.03<br>(30U margin 5x)<br>OCO: TP -12% / SL +10% |
| **C级 轻仓** | 满足A级中3项 (必含均线排列+Supertrend) | 限价SHORT @ 当前×1.05<br>(20U margin 5x)<br>OCO: TP -10% / SL +12% |
| 跳过 | 不满足C级 | 不入场 |

**LONG 质量等级** (镜像逻辑):

| 等级 | 条件 (需全部满足) | 执行动作 |
|------|------------------|----------|
| **A级 满仓** | 1) 1H price > EMA20 > EMA50<br>2) 1H Supertrend = UP<br>3) 1H ADX > 25<br>4) 1H DI+ > DI-<br>5) 5m最近5根 ≥4根阳线 | **市价LONG** (40U margin 5x)<br>OCO: TP +15% / SL -8% |
| **B级 限价** | 满足A级中4项 | 限价LONG @ 当前×0.97<br>(30U margin 5x)<br>OCO: TP +12% / SL -10% |
| **C级 轻仓** | 满足A级中3项 (必含均线排列+Supertrend) | 限价LONG @ 当前×0.95<br>(20U margin 5x)<br>OCO: TP +10% / SL -12% |
| 跳过 | 不满足C级 | 不入场 |

### 第四步：执行与去重

**执行顺序**:
1. 按质量等级排序 (A > B > C)
2. 最多同时持有 **2个A级市价单 + 2个B级限价 + 2个C级限价**
3. 同标的已有持仓/挂单 → 跳过
4. 总风险上限: 所有新仓+挂单potential SL loss ≤ 当前equity的 8%

**持仓后监控** (每cycle重新评估):
- 若持仓标的 1H Supertrend 翻向 → 立即市价平仓 (趋势反转, 不等SL)
- 若持仓标的 1H ADX 跌破 20 → 降级为trail stop (趋势转震荡)
- 若 5m 出现强反转K线 (bull-engulf/three-soldiers on short 或反向) → 减仓50%

### 关键哲学
- **均线 = 真实趋势的骨架**, 比24h涨跌幅有效10倍
- **ADX > 25 = 有效趋势**, 否则只是噪音
- **多指标共振 = 高胜率**, 单一指标 = 赌博
- **A级市价直接打**, 不等待反弹 (真单边趋势不会给好价位)
- **C级限价远离**, 给足缓冲等回踩
- **持仓后trend翻转立即平**, 纪律优先

---

## PHASE 0.4.1 — ★Multi-TF Confluence 交叉验证★ (v3.13, 用户核心教学)

**用户精髓**: "多级别K线结合起来看, 交叉验证, 胜率更高"

### 5级时间框架分工

| 周期 | 任务 | 核心判断 |
|------|------|----------|
| Daily / 6h | 大周期骨架 | Vegas通道排列, 长期趋势结构 |
| 4h / 1h | 趋势验证 | MACD方向, RSI趋势, ADX强度 |
| 30m / 15m | 结构确认 | Swing高低序列, Lower Highs/Higher Lows |
| 5m | 动能确认 | BB位置, 反弹力度, volume |
| 1m | 精准入场 | 反弹衰竭, pinbar, volume climax |

### Confluence 评分规则 (每级20分)

**Daily/6h (+20)**:
```
+20: 方向一致 (空仓+空排列 或 多仓+多排列)
+10: 中性 (均线粘合)
 0: 方向矛盾 (空仓+多排列)
```

**4h/1h (+20)**:
```
+20: MACD方向 + RSI趋势 + Supertrend 全一致
+15: 三者中2个一致
+10: 仅1个一致
 0: 全矛盾
```

**30m/15m (+20)**:
```
+20: 清晰Lower Highs (空) 或 Higher Lows (多) 序列
+15: 有序列但有1次违反
+10: 序列不清晰
 0: 反向序列
```

**5m (+20)**:
```
+20: BB/RSI/MACD动能与方向一致, 不在极端反转区
+15: 2/3一致
+10: 仅1个一致
 0: 全矛盾
```

**1m (+20)**:
```
+20: 清晰入场信号 (pinbar反转 / 量能衰竭 / 突破回踩)
+15: 有信号但不强
+10: 横盘无信号
 0: 反向信号
```

### 入场决策 (按总分)

| 分数 | 等级 | 操作 | 仓位 |
|------|------|------|------|
| ≥ 85 | A+ | 满仓市价进 (不等反弹) | 50U margin |
| 70-84 | A | 半仓市价进 + 限价加仓 | 30U |
| 55-69 | B | 限价单轻仓 (等更好时机) | 15U |
| 40-54 | C | 观察 (不入场) | 0 |
| < 40 | SKIP | 不入场 | 0 |

### 持仓决策 (已有仓)

```
分数 ≥ 60 = 结构仍支持 → 继续持有
分数 40-59 = 结构转弱 → 考虑trailing tight / 减仓50%
分数 < 40 = 结构反转 → 立即平仓出场
```

### 每cycle必跑 (新加到流程最前)

```
cycle开始 →
1. Phase 1: 账户对账
2. Phase 0.4.1: Multi-TF Confluence评分 (BTC + 持仓品种)
3. Phase 0.4.2-0.4.6: 其他结构判断
4. Phase 0.5: 市场context
5. Phase 0.6: Gemma4
...

必输出:
[MTF CONFLUENCE {instId}]
Daily/6h: +{n}/20 — {one line reasoning}
4h/1h:    +{n}/20 — {reasoning}
30m/15m:  +{n}/20 — {reasoning}
5m:       +{n}/20 — {reasoning}
1m:       +{n}/20 — {reasoning}
─────────
Total: {n}/100 = {A+/A/B/C/SKIP}
Direction: {LONG/SHORT/NONE}
Suggested action: {description}
```

---

## PHASE 0.4.2 — Vegas Channel三均线系统 (v3.12, 2026-04-19 用户6h图分析)

**来源**: 用户6h BTC分析用 Vegas Wave 144/169/233 作为"结构生死线"。

### 三均线配置
```
EMA144 (橙) — 中期趋势线
EMA169 (蓝) — 中期确认线
EMA233 (红) — ★长期生死线★
```

### 结构判断规则
```
排列状态:
  多头排列: EMA144 > EMA169 > EMA233 + 价格 > EMA233
  空头排列: EMA144 < EMA169 < EMA233 + 价格 < EMA233
  粘合/混乱: 三线间距 < 2% → 等方向
  
交易方向过滤:
  - 空头排列 → 只做空
  - 多头排列 → 只做多
  - 粘合 → 观望 (不操作)

单边确认:
  - 价格突破EMA233 = 长期方向改变
  - 三线角度加速发散 = 趋势强度加强
```

### 实现 (每cycle计算)
```bash
# 对BTC-USDT-SWAP在6H bar级别计算
python3 -c "
closes = [读取最近250根6h K线 close]
k144 = 2/(144+1); k169 = 2/(169+1); k233 = 2/(233+1)
ema144 = closes[0]
ema169 = closes[0]
ema233 = closes[0]
for c in closes[1:]:
    ema144 = c*k144 + ema144*(1-k144)
    ema169 = c*k169 + ema169*(1-k169)
    ema233 = c*k233 + ema233*(1-k233)
print(f'price={closes[-1]} ema144={ema144:.0f} ema169={ema169:.0f} ema233={ema233:.0f}')
# 输出判断: bull/bear/neutral
"
```

---

## PHASE 0.4.3 — "小实体连续阴线"识别 (v3.12, 用户盘感量化)

**来源**: 用户6h分析"小实体连续阴线 = 下跌中继, 后续大跌概率大"。

### Continuation Contraction Pattern

**公式**:
```python
# 取最近 N+3 根K线 (N=10, 给背景均值)
bars = last_13_candles  # 0=newest

# Body = |close - open|
body = lambda b: abs(b.close - b.open)

# 最近3根实体
b0, b1, b2 = body(bars[0]), body(bars[1]), body(bars[2])

# 背景均实体 (前10根的平均)
avg_body = mean([body(b) for b in bars[3:13]])

is_contraction = (
    # 条件1: 连续3根阴线
    all(bars[i].close < bars[i].open for i in [0,1,2])
    # 条件2: 实体递减
    AND b0 < b1 < b2
    # 条件3: 实体显著小于背景
    AND b0 < avg_body * 0.6
)
```

### 识别后的行动
```
识别到 Continuation Contraction:
  → 信号权重: 空头+8分 (进入评分系统)
  → 预期目标: current × (1 - 最近大阴线幅度 × 1.5)
  → 建议动作: 市价SHORT小仓 + 挂限价在轻微反弹位加仓
  
若识别后K线形态被破坏 (出现大阳线):
  → 立即取消所有pending短单
  → 考虑结构反转
```

### 适用时间框架
- 强信号: 4h / 6h / 12h / Daily (大周期结构)
- 弱信号: 15m / 30m / 1H (小周期, 假信号多)

---

## PHASE 0.4.6 — 目标价测算 + 时间止损 (v3.12, 用户教学)

### 目标价公式 (幅度对称性)
```python
# 找最近10根K线中最大阴线的相对跌幅
last_10_bars = last_10_on_6h  # 或其他合适周期
bearish_bars = [b for b in last_10_bars if b.close < b.open]
max_drop_pct = max([(b.open - b.close)/b.open for b in bearish_bars])

# 目标价 = 当前 × (1 - max_drop × 1.5)
projected_target = current_price × (1 - max_drop_pct × 1.5)
```

### 时间止损 (time-based exit)
```
每个结构性做空/做多持仓设 time_target:
  entry_time + N * bar_period  (N=2-3 bars)
  
例: BTC 6h短, 预期2-3根6h K线到目标
  entry 15:12 + 12h = 次日3:12
  
到时间未达预期:
  - 若仍有浮盈 → 考虑保本出场
  - 若浮亏 → 立即市价平
  - 若在预期区间但未到TP → 继续持有
  
逻辑: 结构性判断有"保质期", 超时未验证 = 分析失效, 止损保本
```

---

## PHASE 0.4.3 — 结构化TP/SL原则（v3.11, 2026-04-19）

**用户教学**: "止赢止损的设置，除了根据张跌幅设置，还可以加入考虑前高、前低的位置，综合考虑。"

### 核心原则
不再用简单百分比（如SL +2%, TP -5%）设止盈止损, 而是**锚定结构位**：

| 元素 | 锚点选择 | 逻辑 |
|------|---------|------|
| **SL (空单)** | 最近swing high + 0.3% | 价格破前高 = 下跌结构失效 |
| **SL (多单)** | 最近swing low - 0.3% | 价格破前低 = 上升结构失效 |
| **TP1 (空单)** | 最近intraday low | 首个目标, 常被测试 |
| **TP1 (多单)** | 最近intraday high | 首个目标 |
| **TP2 (空单)** | 24h low / 前日low | 中期目标, 更深测试 |
| **TP2 (多单)** | 24h high / 前日high | 中期目标 |
| **TP3 (激进)** | BB lowerBand / 关键斐波0.786 | 极限目标 |

### 例子 (RAVE 2026-04-19 15:25)
数据:
- H1=1.534 (recent peak) / H2=1.444 / H3=1.248 (最新swing高)
- 今日low=1.10 (capitulation)
- 24h low=0.941
- 5m BB lower=1.204, 15m BB lower=0.933

限价SHORT @ 1.35 (fib 0.618 bounce):
- ~~百分比法~~: SL +10%=1.485 / TP -25%=1.013
- **结构化法**: SL = H2 1.444 × 1.01 = **1.46** (前高0.01上方)
              TP = 今日low **1.10** (测试回补)
- R/R: (1.35-1.10)/(1.46-1.35) = 0.25/0.11 = **2.27**

### 组合优势
1. **止损更合理**: 基于"如果结构破坏我错了"而非"我能亏多少%"
2. **止盈更精准**: 前低/前高是真实支撑阻力, 常被测试
3. **可视化交易**: 画线能看到SL/TP在图上的含义

### 决策顺序
```
1. 确定方向 (多/空)
2. 找最近swing high和swing low (5m或15m级别)
3. 设SL = 结构破坏位 + 0.3%缓冲
4. 设TP1 = 反向最近swing点
5. 验证R/R ≥ 1.8 (否则skip)
6. 用户教的"激进"情景下, 可加TP2/TP3分层出场
```

### 失效条件
若swing high/low太远 (距离当前价>5%), 且百分比SL会更紧, 则:
- 优先用结构位SL (宁可止损点远)
- 缩小仓位来控制亏损总额
- 不用百分比SL强行拉近 (容易被洗)

---

## PHASE 0.4.4 — 下跌结构中的"Lower High 衰减"规则（v3.10, 用户盘感量化）

**教训来源**: 用户指出挂空@75700"显然不合理"——因为75776已是前高，下一个反弹peak应更低。

### 核心原则
在确认的下跌趋势中：
- 每次反弹的peak **必然低于**前次反弹的peak
- 即 H_N < H_{N-1} < H_{N-2} (单调递减)
- 若反弹突破前高 → **下跌结构被打破**，策略失效

### 量化公式

**Step 1 — 识别最近3个Swing High**:
在30m或15m K线上找最近3个显著高点 (HH pattern):
- H1 = 最远的high（约1-2小时前）
- H2 = 中间的high
- H3 = 最近的high (刚形成)

**Step 2 — 计算下一反弹peak预期 H4**:
```
保守版: H4 = H3 × 0.996      (再低0.4%)
衰减版: H4 = H3 - (H2-H3) × 0.7   (按历史衰减幅度外推)
```
取两者中较低的为entry参考。

**Step 3 — 入场与止损**:
```
入场区:   H4 × 0.995 ~ H4 × 1.005   (±0.5%缓冲)
止损SL:   H3 × 1.003              (前高上方0.3%, 不是远远的H1)
止盈TP:   接近近期low × 0.98       (向下测试新低)
```

### 验证反弹有效性（避免"反弹失败"的尴尬）
```
若当前价格 < H4 × 0.97 (反弹力度不足到H4区)
→ 价格直接走空头续跌, 可考虑:
   - 破位市价短 (如果破前低确认)
   - OR 等下一次反弹机会
```

### 失效触发
```
若价格突破 H3 (前高)
→ 下降结构被破坏, 取消所有空单挂单
→ 重新评估方向
```

### 多时间框架组合
```
30m → 确认下跌结构 (H1>H2>H3)
5m  → 判断当前处于哪一段 (反弹/下跌/盘整)
1m  → 精准入场 (微观反弹peak见顶)
```

### 例子 (BTC 2026-04-19):
- H1 ≈ 76500, H2 ≈ 76100, H3 ≈ 75776 (30m swing highs, 单调递减✓)
- 衰减幅度: 76500→76100 (-400), 76100→75776 (-324)
- 下一衰减预期: -324×0.7 = -227
- **H4 预计 ≈ 75776 - 227 = 75549**
- 入场区: 75500-75600
- SL: 75776 × 1.003 = 76003 (round 76000)
- TP: 74000-74400 (前期低点区)

---

## PHASE 0.4.5 — 高波动标的专属规则（v3.9, 2026-04-19实盘教训驱动）

**教训来源**: RAVE 1.10空单被1.25 SL洗出(-$21), 13.6%SL对53%日内波动币种=送钱。

### 规则1 — 高波动识别
```
高波动标的定义:
  24h波动(high-low)/avg > 30%  (而非24h涨跌)
  或 24h change绝对值 > 40%
```

### 规则2 — 高波动专用SL距离
```
标的类型         SL距离             备注
普通(<20%波动)    1-2×ATR 或 3-5%    标准
中波动(20-30%)   2-3×ATR 或 8-12%   适中
高波动(>30%)     3-5×ATR 或 **20-30%**  RAVE类
极端(>50%)       5×ATR 或 **30-50%**    必须宽
```

**例子**: RAVE 24h波动>50%, 入场1.10的SL应在 **1.55 (+40%)**, 不是1.25(+13.6%).

### 规则3 — 阶梯挂单 (Layered Orders)
对高波动单边标的, 同时挂**3个限价单**:
```
SHORT例子 (价格现价$1.10):
  单1: limit SHORT @ 1.15  sz=10张  (靠近市价, 捕捉小反弹)
  单2: limit SHORT @ 1.30  sz=10张  (中反弹)
  单3: limit SHORT @ 1.50  sz=10张  (大反弹/诱多顶)

共同OCO:
  TP: 当前价 × 0.8  (大目标)
  SL: 当前价 × 1.6  (远stop, 给足空间)
  
优势:
  - 任一fill都有后续支援
  - 反弹越大, 成交越多, 平均价越高 (空单更优)
  - SL统一设在1.6倍价位 (真趋势反转才触发)
```

### 规则4 — Trailing SL for 高波动持仓
```
持仓后按利润梯度移SL:
  profit > 5%  → SL移到 breakeven (入场价)
  profit > 10% → SL移到 入场价 × 0.97  (锁3%)
  profit > 20% → SL移到 入场价 × 0.90  (锁10%)
  profit > 40% → trailing: peak × 1.1 (peak上浮10%)

每次 SL调整通过 okx swap algo amend 执行, 保持OCO有效.
```

### 规则5 — Rolling Orders (SL触发后自动复位)
```
条件: 限价单被SL止损后, 以下全部仍成立:
  1. 标的24h波动仍 > 30%
  2. Phase 0.4趋势指标仍对齐单边方向
  3. 距离上次入场距离 > 25% (避免反复洗)
  
行动: 立即在更远的价位挂新的阶梯限价单
例: RAVE@1.10入场, SL@1.55触发, RAVE pump到1.55+
    → 立即挂 @ 1.70 / 1.90 / 2.10 三层新单
    → 给SHORT继续进场机会
```

### 规则6 — 高波动标的仓位上限
```
单个高波动标的总margin ≤ 60U (vs 普通的30U)
  - 因为SL范围大, 固定亏损金额不变时仓位应缩小
  - 例: SL距离30% × 5x = 150%浮亏 → margin=20U, 最大损失=$30
```

### 综合决策逻辑（AI binding）
```
当Phase 0.4扫到高波动标的 (24h波动>30%):
  1. 用规则2确定SL距离 (不用默认×1.15)
  2. 用规则3挂阶梯 (不挂单层)
  3. 持仓后用规则4做trailing
  4. SL后用规则5评估是否re-entry
  5. 全程遵守规则6仓位上限
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

## PHASE 0.6 — Gemma4 综合市场研判（每 cycle 一次，紧接 Phase 0.5 后）

在 Phase 0.5 并行执行的同时，额外获取多时间框架蜡烛：

```bash
# 并行执行（与 Phase 0.5 同批）
NODE_OPTIONS="--require /Users/jimu/.okx/proxy-inject.cjs" PATH="/opt/homebrew/opt/node@18/bin:$PATH" okx market candles BTC-USDT-SWAP --bar 1D --limit 7 --profile tradebot > /tmp/btc_1d.txt
NODE_OPTIONS="--require /Users/jimu/.okx/proxy-inject.cjs" PATH="/opt/homebrew/opt/node@18/bin:$PATH" okx market candles BTC-USDT-SWAP --bar 12H --limit 7 --profile tradebot > /tmp/btc_12h.txt
NODE_OPTIONS="--require /Users/jimu/.okx/proxy-inject.cjs" PATH="/opt/homebrew/opt/node@18/bin:$PATH" okx market candles BTC-USDT-SWAP --bar 4H --limit 12 --profile tradebot > /tmp/btc_4h.txt
NODE_OPTIONS="--require /Users/jimu/.okx/proxy-inject.cjs" PATH="/opt/homebrew/opt/node@18/bin:$PATH" okx market candles BTC-USDT-SWAP --bar 1H --limit 12 --profile tradebot > /tmp/btc_1h.txt
NODE_OPTIONS="--require /Users/jimu/.okx/proxy-inject.cjs" PATH="/opt/homebrew/opt/node@18/bin:$PATH" okx market candles BTC-USDT-SWAP --bar 5m --limit 20 --profile tradebot > /tmp/btc_5m.txt
```

待 Phase 0.5 数据就绪后，构建综合 Prompt 调用本地 Gemma4（一次调用约 25 秒）：

```bash
python3 -c "
import sys
c1d = open('/tmp/btc_1d.txt').read()
c12h = open('/tmp/btc_12h.txt').read()
c4h = open('/tmp/btc_4h.txt').read()
c1h = open('/tmp/btc_1h.txt').read()
# 注入 Phase 0.5 已知值
prompt = '''You are a senior crypto trading analyst. Analyze BTC-USDT-SWAP across all timeframes.

[DAILY CANDLES - last 7, newest first]
{c1d}

[12H CANDLES - last 7, newest first]
{c12h}

[4H CANDLES - last 12, newest first]
{c4h}

[1H CANDLES - last 12, newest first]
{c1h}

[MARKET INDICATORS]
Supertrend(1H):{st} ADX:{adx} DI+:{dip} DI-:{dim}
MFI(1H):{mfi} Funding:{fr}% Long:{lr}% Short:{sr}%
RSI(5m):{rsi} CCI(5m):{cci}

Determine the macro trend from Daily/12H, then the intermediate trend from 4H/1H.
Identify key support and resistance levels.

Output EXACTLY 11 lines with no extra text:
TREND_DAILY: UP or DOWN or SIDEWAYS
TREND_12H: UP or DOWN or SIDEWAYS
TREND_4H: UP or DOWN or SIDEWAYS
TREND_1H: UP or DOWN or SIDEWAYS
SUPPORT_1: [most critical support as integer]
SUPPORT_2: [second support as integer]
RESISTANCE_1: [most critical resistance as integer]
RESISTANCE_2: [second resistance as integer]
DIRECTION: LONG or SHORT or FLAT
CONFIDENCE: HIGH or MEDIUM or LOW
RISK: [main risk in 10 words max]'''.format(c1d=c1d,c12h=c12h,c4h=c4h,c1h=c1h,...)
print(prompt)
" | ollama run gemma4:e4b 2>/dev/null | col -b > /tmp/gemma4_out.txt
```

**解析输出并更新 state.gemma4_analysis（含新字段）：**
```python
# 从 /tmp/gemma4_out.txt 解析 11 个字段
# 写入 state.json 的 gemma4_analysis:
{
  "trend_daily": "DOWN",
  "trend_12h": "DOWN",
  "trend_4h": "DOWN",
  "trend_1h": "DOWN",
  "support_1": 75700,
  "support_2": 75000,
  "resistance_1": 78300,
  "resistance_2": 76100,
  "direction": "SHORT",   # ← 核心方向判断
  "confidence": "HIGH",
  "updated_at": "..."
}
```

**必须输出：**
```
[GEMMA4 MACRO ANALYSIS {timestamp}]
Daily={TREND} | 12H={TREND} | 4H={TREND} | 1H={TREND}
SUPPORT_1={price} | SUPPORT_2={price}
RESISTANCE_1={price} | RESISTANCE_2={price}
DIRECTION={LONG/SHORT/FLAT} | CONFIDENCE={HIGH/MEDIUM/LOW}
RISK: {text}
→ BTC交易方向: {做多/做空/观望}
→ 入场模式: {见下表}
```

**宏观方向决策（Gemma4 DIRECTION 字段）：**

| Gemma4 DIRECTION | BTC 操作 |
|------------------|---------|
| LONG | 执行 Phase 2C 多单评分逻辑 |
| SHORT | 执行 Phase 2C 空单评分逻辑（Gate/指标取反） |
| FLAT | 跳过新 BTC 入场，仅管理现有持仓 |

**入场门槛由宏观趋势一致性决定：**

| Daily | 12H | 4H | 1H | 模式 | 满仓门槛 | 半仓门槛 |
|-------|-----|----|----|------|----------|----------|
| UP | UP | UP | UP/SW | 强顺势 | ≥65 | 50–64 |
| UP | UP | DOWN | ANY | 回调入场 | ≥70 | 55–69 |
| DOWN | DOWN | DOWN | UP | 逆势短反弹 | ≥82 | 67–81 |
| DOWN | DOWN | DOWN | DOWN | 强逆势/做空 | LONG≥88 / SHORT≥70 | —/55–69 |

---

## PHASE 0.9 — Dynamic SL Algorithm (v3.14, 自适应)

**来源**: Trail SL太紧 (BTC 15点buffer被chop洗) / RAVE SL 0.9%秒被洗 / BASED SL 6%被6.4%反弹打掉

### SL距离公式
```python
def calc_sl_distance(instId, entry_price, direction):
    atr_1m = get_atr(instId, "1m", 14)
    atr_5m = get_atr(instId, "5m", 14)
    vol_24h = (24h_high - 24h_low) / avg * 100  # %
    
    # Base distance
    base_dist = max(
        3 * atr_1m,           # 避免1m chop
        0.3% * entry_price,   # 下限
        2 * atr_5m            # 避免5m noise
    )
    
    # Volatility adjustment
    if vol_24h > 50:     # 极端波动 (RAVE类)
        base_dist *= 3   # → 最少15-25% SL
    elif vol_24h > 30:   # 高波动 (BASED类)
        base_dist *= 2   # → 最少8-15% SL  
    elif vol_24h > 15:   # 中波动 (PIPPIN类)
        base_dist *= 1.5
    # else 标准
    
    # Structure override (final check)
    nearest_swing = get_nearest_structure_point(direction)
    structural_dist = abs(entry_price - nearest_swing) + 0.3% * entry_price
    
    return max(base_dist, structural_dist)
```

### 为不同品种的最低SL距离
| 标的类型 | 24h波动 | 最小SL% |
|---|---|---|
| BTC/ETH | <10% | 1-2% |
| 主流altcoin | 10-20% | 3-5% |
| 中波动 | 20-30% | 8-12% |
| 高波动 | 30-50% | 15-25% |
| 极端(RAVE类) | >50% | **≥25%** 必须 |

### Trail SL 距离 (profit保护)
```
Trail distance = max(
    3 × 1m ATR,           # 避免chop洗出
    current_price × 0.5%, # 最小buffer
    8% * entry_price      # 高vol asset下限
)
```

**铁律**: 永远不使用 **<2% price** SL (除非super低vol)

---

## PHASE 0.95 — Post-Fill OCO Guardian (v3.14, 每cycle必跑)

**来源**: BTC OCO sz=4 vs position=9 有5张裸仓 bug

### 每cycle开始时必跑
```bash
# For each active position
for POSITION in $(get_all_positions); do
    pos_sz=$(get_position_size $POSITION)
    oco_sz=$(get_oco_size $POSITION)
    
    if [ "$oco_sz" == "" ]; then
        # 无OCO, 立即创建
        create_oco_from_memory_params $POSITION
        log "OCO GUARDIAN: Created OCO for ${POSITION} sz=${pos_sz}"
    elif [ "$oco_sz" != "$pos_sz" ]; then
        # OCO size不同步, amend
        amend_oco_size $POSITION $pos_sz
        log "OCO GUARDIAN: Amended ${POSITION} OCO sz ${oco_sz} → ${pos_sz}"
    else
        log "OCO GUARDIAN: ${POSITION} OK sz=${pos_sz}"
    fi
done
```

### 触发场景
- 分层limit filled → 自动sync
- 手动加market order → 自动sync
- OCO被手动cancel → 自动recreate

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

# Candlestick reversal patterns (CLI)
NODE_OPTIONS="--require /Users/jimu/.okx/proxy-inject.cjs" PATH="/opt/homebrew/opt/node@18/bin:$PATH" okx market indicator bull-engulf BTC-USDT-SWAP --bar 5m --profile tradebot
NODE_OPTIONS="--require /Users/jimu/.okx/proxy-inject.cjs" PATH="/opt/homebrew/opt/node@18/bin:$PATH" okx market indicator three-soldiers BTC-USDT-SWAP --bar 5m --profile tradebot

# 30m candles for trend filter (MACD uses 1H - 30m bar not supported by OKX MACD endpoint)
NODE_OPTIONS="--require /Users/jimu/.okx/proxy-inject.cjs" PATH="/opt/homebrew/opt/node@18/bin:$PATH" okx market candles BTC-USDT-SWAP --bar 30m --limit 22 --profile tradebot > /tmp/btc_30m.txt
NODE_OPTIONS="--require /Users/jimu/.okx/proxy-inject.cjs" PATH="/opt/homebrew/opt/node@18/bin:$PATH" okx market indicator MACD BTC-USDT-SWAP --bar 1H --profile tradebot > /tmp/btc_1h_macd.txt

# 5m candles for pattern analysis
NODE_OPTIONS="--require /Users/jimu/.okx/proxy-inject.cjs" PATH="/opt/homebrew/opt/node@18/bin:$PATH" okx market candles BTC-USDT-SWAP --bar 5m --limit 20 --profile tradebot > /tmp/btc_5m.txt
```

**Step 2B.5 — 30m Trend Filter（逆势判断）**

从 `/tmp/btc_30m.txt` 取最近20根30m收盘价，计算EMA20：
```python
k = 2 / (20 + 1)
ema = closes[0]
for c in closes[1:]: ema = c * k + ema * (1 - k)
```

```
if btc_price < ema20_30m:
  → 逆势模式 (counter-trend): 满仓门槛提升至 ≥80，半仓门槛提升至 65-79
else:
  → 顺势模式 (with-trend): 保持标准门槛 ≥70 / 50-69

输出: [TREND FILTER] 30m EMA20={ema:.1f}, price={price}, mode={逆势/顺势}
```

**Step 2B.6a — Pinbar 自动检测（从K线数据直接计算，无需AI）**

```bash
python3 -c "
import re
data = open('/tmp/btc_5m.txt').read()
# OKX candle format: "2026/4/19 02:05:00  open  high  low  close  vol"
# parts[0]=date parts[1]=time parts[2]=open parts[3]=high parts[4]=low parts[5]=close
lines = [l.strip() for l in data.strip().split('\n') if re.match(r'2026', l.strip())]
if lines:
    parts = lines[0].split()
    try:
        o,h,l,c = float(parts[2]),float(parts[3]),float(parts[4]),float(parts[5])
        body = abs(c - o)
        total = h - l
        lower = min(o,c) - l
        upper = h - max(o,c)
        if total > 0:
            if lower >= 2*body and body <= total/3.0 and lower > upper:
                print('PINBAR: BULLISH lower={:.2f} body={:.2f} ratio={:.2f}'.format(lower,body,lower/max(body,0.01)))
            elif upper >= 2*body and body <= total/3.0 and upper > lower:
                print('PINBAR: BEARISH upper={:.2f} body={:.2f} ratio={:.2f}'.format(upper,body,upper/max(body,0.01)))
            else:
                print('PINBAR: none')
        else:
            print('PINBAR: none')
    except: print('PINBAR: none')
else:
    print('PINBAR: none')
" > /tmp/btc_pinbar.txt
cat /tmp/btc_pinbar.txt
```

解析规则（比较当前价格与 gemma4_analysis.support_1）：
- `PINBAR: BULLISH` 且当前价格在 `support_1 * 0.985 ~ support_1 * 1.015`（支撑位±1.5%） → **关键支撑位Pinbar**，高价值信号
- `PINBAR: BULLISH` 但不在支撑位附近 → 普通Pinbar，参考价值
- `PINBAR: BEARISH` → 做多时为负面信号
- `PINBAR: none` → 无Pinbar

**Step 2B.6b — Gemma4 扩展K线形态识别（本地AI辅助，与2B.6a互补）**

在Pinbar检测之后，用本地Gemma4识别更复杂的多K线形态（晨星、穿刺线等）：
```bash
echo "BTC-USDT-SWAP 5m OHLC candles (newest first, format: time open high low close vol):
$(cat /tmp/btc_5m.txt)

Task: Identify multi-candle bullish reversal patterns ONLY (morning star, bullish harami, piercing line, tweezer bottom, three white soldiers). Single-candle patterns are already handled. Reply with exactly one line: PATTERN: [pattern_name] or PATTERN: none" \
  | ollama run gemma4:e4b 2>/dev/null \
  | col -b | grep "PATTERN:" | tail -1 > /tmp/gemma4_pattern.txt
cat /tmp/gemma4_pattern.txt
```

解析规则：
- 输出含 `PATTERN: none` 或文件为空 → Gemma4无多K线形态
- 输出含具体形态名 → Gemma4检测到多K线形态

⚠️ 若ollama未启动，跳过2B.6b，仅使用2B.6a Pinbar结果。响应通常需要20-30秒。

**Step 2B.6c — 1H MACD 顶背离检测（持仓风险监控）**

注意：OKX MACD指标端点不支持30m时间框架，改用1H（`/tmp/btc_1h_macd.txt`）。

仅当 `state.btc_position.active == true` 时执行：
```bash
python3 -c "
import re
# 解析 /tmp/btc_1h_macd.txt 获取最近10个DIF值（1H MACD，OKX不支持30m）
data = open('/tmp/btc_1h_macd.txt').read()
# 假设格式包含 dif 字段，提取最近值
difs = re.findall(r'dif[\":\s]+(-?[\d.]+)', data, re.IGNORECASE)
difs = [float(x) for x in difs[:10]]

# 解析 /tmp/btc_30m.txt 获取最近10根收盘价
price_data = open('/tmp/btc_30m.txt').read()
price_lines = [l.strip() for l in price_data.strip().split('\n') if re.match(r'[0-9]', l.strip())]
closes = [float(l.split()[4]) for l in price_lines[:10] if len(l.split()) >= 5]

if len(difs) >= 6 and len(closes) >= 6:
    # 找最近的两个价格高点（swing high）
    swing_highs = []
    for i in range(1, len(closes)-1):
        if closes[i] > closes[i-1] and closes[i] > closes[i+1]:
            swing_highs.append((i, closes[i], difs[i] if i < len(difs) else None))
    
    if len(swing_highs) >= 2:
        sh1, sh2 = swing_highs[-2], swing_highs[-1]  # sh2 is more recent
        if sh2[2] is not None and sh1[2] is not None:
            if sh2[1] > sh1[1] and sh2[2] < sh1[2]:  # Price HH but MACD LH
                print('MACD_DIV: BEARISH price_sh1={:.0f} price_sh2={:.0f} dif_sh1={:.2f} dif_sh2={:.2f}'.format(sh1[1],sh2[1],sh1[2],sh2[2]))
            else:
                print('MACD_DIV: none')
        else:
            print('MACD_DIV: insufficient_dif_data')
    else:
        print('MACD_DIV: insufficient_swings')
else:
    print('MACD_DIV: insufficient_data')
" > /tmp/btc_macd_div.txt
cat /tmp/btc_macd_div.txt
```

### Step 2C — BTC Entry Weighted Scoring (total 100 pts)

**Only if no active BTC position** (`state.btc_position.active == false`):

**Gate condition** (must pass before scoring): `rsi_5m < 45` AND `cci_5m < -60`
Gate fails → output skip reason and stop. Gate passes → proceed to full scoring.

**趋势门槛调整（来自Step 2B.5的逆势/顺势模式）：**
| 模式 | 满仓门槛 | 半仓门槛 | 说明 |
|------|----------|----------|------|
| 顺势 (btc_price ≥ 30m EMA20) | ≥70 | 50–69 | 标准门槛 |
| 逆势 (btc_price < 30m EMA20) | **≥80** | **65–79** | 下跌趋势中抄底需更强信号 |

**Weighted scoring table (8 dimensions, 100 pts total):**

| # | Dimension | Weight | Scoring Rules |
|---|-----------|--------|---------------|
| 1 | RSI 5m (momentum depth) | **15 pts** | <30→15 / <35→12 / <40→9 / <45→5 / ≥45→0 |
| 2 | CCI 5m (oscillator depth) | **15 pts** | <-150→15 / <-100→12 / <-80→8 / <-60→4 / ≥-60→0 |
| 3 | MFI 5m (capital outflow) | **15 pts** | <30→15 / <40→11 / <50→6 / ≥50→0 |
| 4 | Supertrend 1H (trend) | **15 pts** | UP→15 / DOWN→0 |
| 5 | Long/Short ratio (positioning) | **10 pts** | short>65%→10 / short>55%→6 / balanced→3 / long>55%→0 |
| 6 | Funding rate (market bias) | **10 pts** | <-0.02%→10 / <-0.01%→7 / ±0.01%→4 / >0.02%→0 |
| 7 | K线形态+热点共振 | **10 pts** | Pinbar在support_1±1.5%→10 / CLI(bull-engulf/three-soldiers)→8 / Pinbar非关键位→6 / Gemma4多K线形态→6 / 价格在support_1±0.5%且30mEMA20±0.5%热点共振→+2叠加(上限10) / 全无→0 |
| 8 | Gemma4综合判断 | **10 pts** | BIAS=BULLISH+HIGH→10 / BULLISH+MEDIUM→8 / NEUTRAL+HIGH→5 / NEUTRAL+MEDIUM→3 / BEARISH→0 |

**Total = sum of all 8 dimensions = max 100 pts**

**AI must output the scoring block:**
```
[BTC入场加权评分]
① RSI={值}           → {分}/15分
② CCI={值}           → {分}/15分
③ MFI={值}           → {分}/15分
④ Supertrend={方向}   → {分}/15分
⑤ 多空比=多{%}/空{%}  → {分}/10分
⑥ 资金费率={值}       → {分}/10分
⑦ K线形态={结果}      → {分}/10分
⑧ Gemma4={BIAS/CONF} → {分}/10分
──────────────────────────────
总分: {分}/100分
入场模式: {强顺势/震荡反弹/短线反弹/强逆势}（来自Phase 0.6）
决策: {满仓/半仓/跳过}（门槛见 Phase 0.6 表格）
保证金: {200U / 100U / 0U}
推理: [2-3句：关键支撑维度，拖分维度，最大风险]
```

**Execution — 方向由 Phase 0.6 Gemma4 DIRECTION 决定：**

**做多（DIRECTION=LONG）：** Gate: rsi_5m < 45 AND cci_5m < -60
```bash
NODE_OPTIONS="--require /Users/jimu/.okx/proxy-inject.cjs" PATH="/opt/homebrew/opt/node@18/bin:$PATH" okx swap leverage --instId BTC-USDT-SWAP --lever 50 --mgnMode isolated --posSide long --profile tradebot
# 验证: okx swap get-leverage --instId BTC-USDT-SWAP --mgnMode isolated --profile tradebot
okx swap place --instId BTC-USDT-SWAP --side buy --ordType market \
  --sz {sz} --posSide long --tdMode isolated --tag agentTradeKit --profile tradebot
```

**做空（DIRECTION=SHORT）：** Gate: rsi_5m > 55 AND cci_5m > 60
- 评分规则取反：RSI>70→15 / RSI>65→12 / RSI>60→9 / RSI>55→5
- CCI>150→15 / CCI>100→12 / CCI>80→8 / CCI>60→4
- MFI>70→15 / MFI>60→11 / MFI>50→6
- Supertrend DOWN→15 / UP→0
- K线形态：bear-engulf/three-ravens=1 → 10pts（CLI反向形态）
- Gemma4 DIRECTION=SHORT+CONFIDENCE=HIGH → 10pts

```bash
NODE_OPTIONS="--require /Users/jimu/.okx/proxy-inject.cjs" PATH="/opt/homebrew/opt/node@18/bin:$PATH" okx swap leverage --instId BTC-USDT-SWAP --lever 50 --mgnMode isolated --posSide short --profile tradebot
okx swap place --instId BTC-USDT-SWAP --side sell --ordType market \
  --sz {sz} --posSide short --tdMode isolated --tag agentTradeKit --profile tradebot
```

空单止损：`sl_price = avg_entry * 1.012`（价格上涨1.2%止损）
空单止盈：TP① RSI<30 OR CCI<-80 减仓20%；TP② RSI<25 全平

门槛仍按宏观趋势一致性表格执行（见 Phase 0.6）。

**DIRECTION=FLAT**：跳过所有新 BTC 入场。

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

**入场后立即挂 OCO 原生止损止盈（OKX 平台硬止损，断网/宕机也会执行）：**
```
sl_price = avg_entry_price * 0.988          # 入场价 -1.2%
tp_price = state.gemma4_analysis.resistance_1  # Gemma4 最近阻力位
```
```bash
NODE_OPTIONS="--require /Users/jimu/.okx/proxy-inject.cjs" PATH="/opt/homebrew/opt/node@18/bin:$PATH" okx swap algo place \
  --instId BTC-USDT-SWAP --side sell --sz {total_sz} --ordType oco \
  --tpTriggerPx {tp_price} --tpOrdPx=-1 \
  --slTriggerPx {sl_price} --slOrdPx=-1 \
  --posSide long --tdMode isolated --reduceOnly \
  --tag agentTradeKit --profile tradebot
```
将返回的 `algoId` 存入 state: `"btc_oco_algoId": "{algoId}"`。
OCO 触发后自动全平12张，无需 Step 2D 手动止损。

### Step 2D — BTC Exit Logic

**Only if active BTC position** (`state.btc_position.active == true`):

```bash
NODE_OPTIONS="--require /Users/jimu/.okx/proxy-inject.cjs" PATH="/opt/homebrew/opt/node@18/bin:$PATH" okx market indicator RSI BTC-USDT-SWAP --period 14 --bar 5m --profile tradebot
NODE_OPTIONS="--require /Users/jimu/.okx/proxy-inject.cjs" PATH="/opt/homebrew/opt/node@18/bin:$PATH" okx market indicator CCI BTC-USDT-SWAP --period 20 --bar 5m --profile tradebot
NODE_OPTIONS="--require /Users/jimu/.okx/proxy-inject.cjs" PATH="/opt/homebrew/opt/node@18/bin:$PATH" okx market ticker BTC-USDT-SWAP --profile tradebot
NODE_OPTIONS="--require /Users/jimu/.okx/proxy-inject.cjs" PATH="/opt/homebrew/opt/node@18/bin:$PATH" okx swap algo orders --instId BTC-USDT-SWAP --profile tradebot
```

**⚡ OCO 原生止损优先（OKX 平台级，断线也生效）:**

首先检查 `state.btc_oco_algoId` 是否存在且algo orders中仍有效：
- 若 OCO 已触发（orders为空 + 仓位消失）→ 清除 state btc_position，更新 peak_equity，跳过后续手动逻辑
- 若 OCO 存在但 Gemma4 更新了 resistance_1 或 support_1 → 用 `okx swap algo amend` 更新触发价

若 OCO 不存在（遗漏或已取消），立即补挂：
```bash
NODE_OPTIONS="--require /Users/jimu/.okx/proxy-inject.cjs" PATH="/opt/homebrew/opt/node@18/bin:$PATH" okx swap algo place \
  --instId BTC-USDT-SWAP --side sell --sz {total_sz} --ordType oco \
  --tpTriggerPx {resistance_1} --tpOrdPx=-1 \
  --slTriggerPx {avg_entry * 0.988} --slOrdPx=-1 \
  --posSide long --tdMode isolated --reduceOnly \
  --tag agentTradeKit --profile tradebot
```

**Stop Loss B（备用，当 OCO 意外失效时）— Gemma4 支撑位跌破止损:**
```
support_1 = state.gemma4_analysis.support_1
if btc_price <= support_1 AND state.gemma4_analysis.trend_1h == "DOWN":
    → 取消 OCO：okx swap algo cancel --instId BTC-USDT-SWAP --algoId {btc_oco_algoId}
    → 立即全平（支撑位破位，下跌加速风险）
    → 日志: "SUPPORT BREAK STOP: price={price} broke support_1={support_1}"
```

若手动触发全平：
```bash
NODE_OPTIONS="--require /Users/jimu/.okx/proxy-inject.cjs" PATH="/opt/homebrew/opt/node@18/bin:$PATH" okx swap place --instId BTC-USDT-SWAP --side sell --ordType market \
  --sz {state.btc_position.total_sz} --posSide long --tdMode isolated --reduceOnly \
  --tag agentTradeKit --profile tradebot
```
Clear btc_position and btc_oco_algoId from state.

**TP0 — 价格过度延伸（均值回归，优先级高于常规TP）:**
```
获取30m EMA20值（来自/tmp/btc_30m.txt的最新收盘价序列计算，或从已有指标估算）：
if btc_price > ema20_30m * 1.030:
    → 价格偏离30mEMA20超过3%，均值回归概率高
    → 触发TP① (减仓20%)，日志: "OVEREXTENSION TP0: price={price} > EMA20*1.03={threshold}"
```

**TP1.5 — MACD 1H 顶背离（动量衰竭信号，优先级高于常规TP①）:**
```
读取 /tmp/btc_macd_div.txt：
if contains "MACD_DIV: BEARISH":
    → 1H MACD顶背离，价格创新高但MACD动量下降，上涨动力衰竭
    → 触发TP① (减仓20%)，日志: "MACD_DIV TP1.5: bearish divergence detected on 1H"
```

**动态止盈阈值（根据 Gemma4 BIAS 自动调整）：**

| Gemma4 BIAS | TP① 触发 | TP② 触发 | TP 目标参考 |
|-------------|---------|---------|-----------|
| BULLISH | CCI > 100 | RSI > 70 | 标准（顺势持有更久）|
| NEUTRAL | CCI > 90 | RSI > 67 | 略保守 |
| BEARISH | CCI > 80 | RSI > 63 | 保守（反弹随时结束）|

BEARISH 时额外规则：若价格触及 `state.gemma4_analysis.resistance_2` → 视同 TP① 触发（取决于哪个先发生）。

**Take Profit ① — CCI > {动态阈值}** (if `remaining_pct == 100`):

AI must output reasoning before executing:
```
[BTC TP① 推理]
CCI={值} 超买（当前阈值={动态阈值}，BIAS={BIAS}）。未实现盈亏={uPnL}U。
评估：{反弹幅度是否接近RESISTANCE_2；BEARISH模式下应保守减仓}
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

**Take Profit ② — RSI > {动态阈值}** (close ALL remaining):

AI must output reasoning before executing:
```
[BTC TP② 推理]
RSI={值} 超买（当前阈值={动态阈值}，BIAS={BIAS}）。
持仓均价={avg}，当前价={price}，盈利={profit_pct:.1f}%。
评估：{若BEARISH模式，当前是否接近resistance_1；综合判断出场合理性}
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

## PHASE 2.6 — RAVE Wick Hunter (v3.14, 高波动insta-spike狙击)

**Motivation**: 今日RAVE多次秒级插针 (+5-10%单根K线), 本应重仓做空但我错过。此模块**专门**捕捉插针做空。

### Trigger 条件 (AI综合评估)
当 **RAVE当前价 < 1.30** (处于下跌结构末期) 且 **触发条件任一**:

**T1 — 大上影wick**:
- 最近1m K线: `(high - max(open,close)) / close > 3%`
- 即上影>3%且收盘回到实体

**T2 — 单根intrabar spike**:
- 最近3根1m任一: `(high - low)/open > 5%`
- 说明market内正在剧烈波动

**T3 — 近期大阻力wick到**:
- 当前价 touch近期 (30min内) 重要阻力 (H2/H3/5m BB upper) 但未收盘突破
- 典型"fake breakout"模式

### AI Decision Layer (必须, 比赛合规)

每次trigger发生, AI评估:
```
[RAVE WICK HUNTER {时间}]

Input:
  - Trigger type: T1/T2/T3
  - Current price: {price}
  - 1m bar pattern: {OHLC最近5根}
  - 5m Supertrend: {UP/DOWN}
  - 15m Supertrend: {UP/DOWN}
  - 1H Supertrend: {UP/DOWN}
  - Float PnL全仓: {amount}
  - Account health: {equity}
  - 距24h low: {pct}

AI Synthesis (必须文字):
  评估1: 这是"真rejection"还是"假wick后趋势反转"?
  评估2: 重仓做空 vs 试探仓?
  评估3: 入场方式 — 市价 (wick正在发生) vs 限价 (等next wick)?
  评估4: 当前全仓暴露, 加空否?

Final decision: {GO_HEAVY | GO_SMALL | SKIP}
Position sizing:
  - GO_HEAVY: 40U margin × 5x = $200 notional (≈150-160 RAVE contracts)
  - GO_SMALL: 20U margin × 5x = $100 notional
Entry:
  - 若spike正在发生 → market short 立即
  - 若刚rejected → limit at 95% of wick high (等小反弹)
SL: wick的最高价 × 1.12 (12% buffer, 符合v3.14高vol规则)
TP: 24h low × 1.02 (大目标, 激进)

Confidence: {0-1}
Risk assessment: 若SL触发最大损失 {amount}
```

### 限价埋伏 (Pre-Placed Wick Traps)

预先挂单在可能的wick高位, 实现**零延迟捕捉**:

```
For RAVE (current ~1.20):
  - 限价SHORT @ 1.35 (近期wick peak)
  - 限价SHORT @ 1.50 (大wick target)
  - 限价SHORT @ 1.75 (极端wick, 抓一次就赚大)
  
每个单独OCO:
  TP: 1.00 (统一大目标)
  SL: entry × 1.15 (符合高vol rule)
  sz: 5-10张 (每单15-30U margin)
```

**优势**: 限价不fill=零风险; 只要wick触及, 立即成交并带OCO保护。

### 风控
- 本Phase最大total allocation: 80U margin (即便3层全fill)
- 24h RAVE波动>50% 则启用此phase
- RAVE持仓 + wick hunter 总仓位max 150U margin
- 若equity < 550U, 停止Wick Hunter (保护剩余资金)

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

6. **MACD Head-and-Shoulders Top (4H/1H)**: In the last 20 candles of 4H or 1H MACD, find 3 DIF peaks where peak1 < peak2 (left shoulder < head) AND peak3 < peak2 (right shoulder < head). This signals Elliott Wave 5 completion / exhaustion top. A right shoulder where DIF failed to reach the head level = distribution phase ending → strong short signal. Extra weight: if peak3 < peak1 also (classic 头肩顶), add +1 to signal_count.

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

## Execution Order Summary (v3.14 with AI Decision Layer)

```
Every cycle (dynamic paced):
│
├─ 1. Load state.json
├─ 2. PHASE 0.95: OCO Guardian ← 必跑 (同步所有仓位OCO sz)
├─ 3. Account check (balance + positions + bots)
│
├─ 4. PHASE 0.1: AI层初始化 — Claude开始本cycle决策会议
├─ 5. PHASE 0.2: Macro Bear Filter ← grid保护
│   ├─ 若macro_bearish: 降级grid操作
│   └─ 否则: 正常运行
│
├─ 6. PHASE 0.4: 动态单边高波动扫描 (all SWAP市场)
├─ 7. PHASE 0.5: Market Context Assessment ← NEW
│   ├─ Supertrend + ADX → trend direction & strength
│   ├─ BBWidth + HV → volatility regime
│   ├─ MFI + Funding + Long/Short ratio → capital flow & positioning
│   ├─ BTC sentiment → crowd behavior
│   └─ OUTPUT: structured market context + confidence baseline
│
├─ 4. PHASE 2: BTC Strategy
│   ├─ Not activated? → check 1H DIF → activate if near zero
│   ├─ No position? → 30m EMA20 trend filter → 逆势模式 or 顺势模式
│   │   → 7-dimension 100-pt weighted scoring (RSI+CCI+MFI+Supertrend+L/S+funding+candle)
│   │   → ⑦含Gemma4扩展识别 (ollama run gemma4)
│   │   ├─ 顺势: Score ≥70→200U / 50-69→100U | 逆势: ≥80→200U / 65-79→100U | 否则skip
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
- **Gemma4 timeout**: If ollama call exceeds 30s or fails, use last cached `state.gemma4_analysis`; log "GEMMA4 CACHED". If no cache exists, default to NEUTRAL/MEDIUM.

---

## Self-Iteration Protocol（策略自我迭代）

**授权范围**：AI 可在执行过程中直接修改以下内容，无需用户确认：
- 评分维度的权重（±5分以内，保持总分=100）
- TP/SL 百分比阈值（±0.2%以内）
- 动态 TP 的 RSI/CCI 触发阈值（±10以内）
- Phase 0.6 Gemma4 prompt 措辞优化
- 新增/删除网格候选评估规则

**需要用户确认**：
- 改变核心仓位上限（400U BTC / 100U 网格）
- 改变杠杆倍数
- 新增做空 BTC 逻辑
- 任何可能增加爆仓风险的修改

**迭代记录**：每次修改必须在 `/Users/jimu/okx-compound-strategy/runner/strategy_log.md` 追加一条记录：
```
## {timestamp} - v{version} 自动迭代
**修改内容**: {具体改动}
**触发原因**: {观察到的现象或模式}
**预期效果**: {改动目标}
**回滚方式**: {如何恢复原值}
```

**迭代原则**：
1. 观察到某个指标在多个 cycle 中持续误导决策 → 调低其权重
2. 某个 Gemma4 输出字段与后续价格行为高度一致 → 增加对应维度权重
3. 止盈过早导致错过大行情 → 适度提高 TP 阈值
4. 止盈过晚导致回吐利润 → 适度降低 TP 阈值
5. 任何修改都必须基于至少 3 个 cycle 的观察，不基于单次误差
