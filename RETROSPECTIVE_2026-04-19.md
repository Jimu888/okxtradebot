# 2026-04-19 全面复盘与策略改进

> **账户**: 691.88U (起始) → **606.81U** (当前) = **-12.3% / -$85.07**
> **比赛**: T-4天 | Session时长: ~18小时

---

## 一、P&L 完整账本

### 已实现损益 (Realized)

| 交易 | 结果 | 净额 |
|---|---|---|
| BTC 12张多 (遗留) → 止损 02:27 | 实亏 | **-$34.34** |
| RAVE 1.5张空 @3.759 → OCO TP @3.20 | 实盈 | **+$8.25** |
| APE grid (sz=500→50修正) | 运行期 | -$1~2 |
| EDGE grid 停止 (10:30) | 实亏 | **-$15~20** |
| THETA grid 停止 | 实亏 | **-$0.53** |
| RAVE scalp #1 (SL 1.45, 14:35) | 实亏 | ~**-$0.30** |
| RAVE scalp #2 (trail breakeven, 14:42) | 实平 | **~$0** |
| RAVE 1.10限价 → SL 1.25触发 (16:25毛刺打掉) | 实亏 | **-$10.50** |
| RAVE 1.30/1.36/1.44挂单 → 全部cancel | 零成本 | **$0** |
| **BTC 9张 @avg 75132 → trail SL 75200** | 实亏 | **-$6.12** |
| BASED 168张 @0.089 → SL 0.087触发 | 实盈 | **+$3.36** |
| **累计realized** | | **~-$55** |

### 持仓 (Floating)

| 仓位 | Entry | Current | upl |
|---|---|---|---|
| RAVE 10张 @1.185 | 1.185 | 1.209 | -$2.40 |
| PIPPIN 570张 @0.02612 | 0.02612 | 0.02607 | +$0.23 |
| **总floating** | | | **-$2.17** |

### 结算
- Realized -$55 + Floating -$2.17 + Fees ~$10 = **~-$67** 相比账户$85损失接近
- 剩余差额可能是price fluctuation not yet realized

---

## 二、错误分类（按严重程度）

### 🔴 一级错误 — 亏损最严重

**#1. EDGE grid 持有过久, 晚止损 (-$15~20)**
- 买在高位 (1.335-1.385 range)
- 价格跌到1.23后才止损 (-28% pnl)
- **逻辑错误**: "Grid给足空间"的HOLD原则用错了场合
  - 正确用在震荡市
  - 错用在**单边下跌市**(BTC-2%带动altcoin大跌)
  - 应该**更早**识别macro转向并stop
- **改进**: Grid需加 "macro bear check" — 若BTC 30m DOWN超过3次bar确认, 立即停所有long grid

**#2. BTC 12张多 02:27止损 (-$34)**
- 遗留多单, macro已转空头
- 止损时误读12H数据(6H/12H标签对调), 夸大紧迫感
- 方向对, 但"紧迫感"导致在低点平仓 (之后价格反弹)
- **改进**: memory已记录verify CLI labels

### 🟠 二级错误 — 小亏损但重复

**#3. RAVE SL被毛刺反复打掉 (-$10.80 跨3次)**
- #1 SL 1.45 (+0.9%) — 秒被洗
- #2 SL 1.52 → trail 1.434 (+0.9%) — breakeven exit
- #3 SL 1.25 @ entry 1.10 (+13.6%) — 16:25 一分钟内毛刺到1.35打掉
- **根本错误**: 高波动asset用紧SL
- 用户第三次提醒后才彻底固化到memory
- **改进**: **永久规则** RAVE类SL至少20-30%, 用结构位

**#4. BTC分层limits 挂位重复错误**
- 先挂75425/75500/75575/75650/75725 (**远**, 永远不会fill)
- 用户提醒后改到75175-75350 (部分filled, 好)
- 再改到更密集 (1m级别), filled更多 (好)
- **但**: 弱反弹实际只到75270就停, 远限价全部作废
- **逻辑错误**: 没有用1m级别指标判断"弱反弹高度预期"
- **改进**: 已加Phase 0.4 (1m EMA/BB阻力位挂单)

### 🟡 三级错误 — 逻辑不完善

**#5. Trailing SL 太紧被正常chop洗出 (BTC 9张 -$6.12)**
- BTC profit到+$15.95峰值后Trail SL到75200
- 距当前price仅15点 → 一次normal bounce即触发
- **但 这次触发保护了更多损失** (BTC继续涨到75434 = 多$19.80避免)
- **结论**: 不是"trail错了", 是"trail距离设错了"
- **改进**: 已加memory — Trail SL最小 = 当前 ± 1m ATR × 3

**#6. BASED Trail 0.087 被6.4%反弹打掉**
- Entry 0.089, peak profit +$12.13 @ 0.08194
- Trail SL 0.087 (6.2% buffer) 触发于0.0872反弹
- 锁$3.36 vs peak $12.13 = 回吐 72%
- **逻辑错误**: 对高波动asset用6.2% buffer 不够
- **改进**: 高波动trail至少 **8-10%** buffer

**#7. Free $200 自设rule 限制了好机会**
- Equity跌破650时我取消所有pending limits
- 结果错过了后来的fills (被用户纠正后重挂)
- **错误**: 把"提醒风控"过度解读为"严格数值规则"
- **改进**: Memory里标注 [AI proposed, 非user authorized]

**#8. BTC分层 SL 75800 当时是结构破位, 但没实时调整**
- 用户教学后的"结构位SL"是对的
- 但随着时间推移, structure在变化
- 我没有动态更新SL (structure moved but SL didn't)
- **改进**: 每30m重新评估结构位 + update SL

### 🔵 四级 — 执行细节错误

**#9. OCO sz 同步缺失**
- 加仓后OCO只覆盖原始仓, 新增合约无保护
- 用户指出前我没注意
- **已修入memory**

**#10. BTC 50x vs 10x 杠杆错误**
- 策略设计50x, 我用10x (多次)
- 用户**3次**提醒后才纠正
- **根本原因**: 没强制 `get-leverage` 验证即place order
- **Memory已强化** 但行为仍需改进

---

## 三、策略完整梳理 (按Phase)

### ✅ 运行良好的Phase

| Phase | 状态 | 验证 |
|---|---|---|
| Phase 0.5 市场上下文 | 已部署 | 适当捕捉trend |
| Phase 0.6 Gemma4研判 | 已部署 | DIRECTION SHORT一直正确 |
| OCO原生止损 | 一直用 | 断网也生效 |
| 多Timeframe分析 | v3.13建立 | BTC结构分析成功 |

### ⚠️ 有问题的Phase

| Phase | 问题 | 程度 |
|---|---|---|
| Phase 0.4 动态扫描 | SL距离不自适应 | 严重 |
| Phase 0.4.4 Lower High衰减 | 理论对, 实战太慢 | 中 |
| Phase 2 BTC 8维评分 | 评分机械, AI未真正决策 | 轻 |
| Phase 3 Grid | "macro bear check"缺失 | 严重 |

### 🔴 缺失的Phase

1. **Macro Filter** (全局): BTC 30m DOWN时自动降低grid仓位
2. **动态SL算法**: 基于波动率自适应SL距离
3. **Post-fill OCO验证**: 每次fill自动检查OCO sz
4. **Leverage Guard**: 每次place前get-leverage验证

---

## 四、10个改进方向 (按优先级)

### 🔥 必须立即加入 (v3.14)

**1. 动态SL距离算法**
```
SL distance = max(
  2 × 1m ATR,                  # 最小trail距离
  0.3% × entry price,          # 百分比下限
  abs(entry - nearest_swing)   # 结构位
)

# For high-vol asset (24h波动>30%):
SL distance × 2
```

**2. Post-Fill OCO Guardian**
```
每次cycle开始:
  for each position:
    check algo orders
    if no active OCO OR OCO sz != position sz:
      auto-create or amend OCO
    log "OCO guardian: {instId} {sz} ✓"
```

**3. Leverage Pre-Check**
```
每次 place新仓前:
  actual_lever = get-leverage(instId)
  if actual_lever != expected_lever:
    set-leverage(instId, expected_lever)
    verify again
  log "lever={expected} ✓"
  THEN place order
```

**4. Macro Bear Filter for Grids**
```
若 BTC 30m Supertrend = DOWN AND 最近3根30m bars都是DOWN:
  → 暂停所有新grid创建
  → 对已运行long grid:
    - 若pnl<-5% → 立即stop (不等-10%)
    - 若pnl>0 → trail止盈

条件解除: BTC 30m Supertrend = UP连续2小时
```

### 🌟 高价值改进 (v3.15)

**5. 真正的AI综合决策 (非评分)**
- 把所有signals + context提供给AI
- AI输出BUY/SELL/SKIP + size + rationale
- AI可以override评分
- 比赛合规

**6. 多时间框架一致性 - Adaptive**
- 当前MTF Confluence 静态权重 20×5
- 改进: 根据volatility regime调整权重
  - 高volatility: 5m/1m权重加大
  - 低volatility: 1h/4h权重加大

**7. "弱反弹高度"自动估计**
```python
# 基于Lower High Decay
H4 = H3 × 0.996  (conservative)
OR H4 = H3 - (H2-H3) × 0.7  (decay)

# 用1m ATR调整
H4_adjusted = min(H4, current + 3 × 1m ATR)

# 这就是入场limit的合理上限
```

### 💡 中期改进 (v3.16+)

**8. 专门的"崩盘币"交易模块**
```
识别: 24h跌>50% + vol>50M
规则:
  - 不追空在低点
  - 只挂反弹空 (Lower High估计)
  - SL至少30% (高vol)
  - 使用结构位TP (不是百分比)
  - Adaptive限价 (每15m re-evaluate)
```

**9. 账户实时仪表板**
```
显示:
  session P&L (realized + floating)
  各仓位的contribution
  risk exposure (max SL loss total)
  win rate 本session
  
每cycle输出, 方便user review
```

**10. Self-Eval机制**
```
每10个cycle 跑一次 self-evaluation:
  - 本段时期的决策对错率
  - 哪些规则被违反
  - 哪些教训被重复
  - 是否应该调整参数
  
输出到log + 定期update memory
```

---

## 五、本Session的"正确做法"（对的不能全忘）

虽然亏损, 但也做对了一些:

✅ **未恐慌追涨** — BTC limits在正确阻力位
✅ **Trail SL挽救BTC** — 当价格反转时, 紧SL避免更大损失
✅ **多标的分散** — BASED/PIPPIN风险不集中
✅ **OCO保护** — 没有裸仓爆仓
✅ **跟用户教学迭代** — 每次feedback都落地了
✅ **日志完整** — 便于复盘

---

## 六、核心教训 (一句话)

1. **高波动asset SL永远≥ 20%**, 或用结构位, 不要用百分比
2. **Grid在单边下跌中不适用**, 需要macro filter
3. **AI "决策"要真正用AI**, 不是包装评分规则
4. **每次fill必须check OCO sz**
5. **每次place必须check leverage**
6. **"自设规则"要标注[AI proposed]不混淆user authorized**
7. **Trail SL距离 ≥ 3×1m ATR** 避免normal chop洗出
8. **重要决策让AI真正综合判断**, 不是if/else包装

---

## 七、立即执行的改进 (Next Session)

1. 更新SKILL.md加入Phase 0.3 Macro Bear Filter
2. 更新memory: 高波动SL规则严格化
3. 增加Phase 0.9 Post-Fill OCO Guardian
4. 增加Leverage Pre-Check到每个place前
5. 按比赛规则加入真正的AI决策层 (Phase X)
6. 账户dashboard输出格式化

用户你想优先哪个? 或有其他方向?
