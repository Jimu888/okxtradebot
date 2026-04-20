---
name: OKX策略睡眠期自主授权
description: 用户睡眠期间授权Claude自主执行/迭代OKX复合策略v3.6的规则和风控底线
type: feedback
originSessionId: 6819a028-0276-4380-923a-fa92dcc807e6
---
用户睡觉时授权我自主执行和迭代OKX复合策略（2026-04-19 03:xx授权）。

**可做的**：
- 策略迭代：发现改进点可直接更新 SKILL.md + 记录 strategy_log.md
- 多空都可以做（BTC/ETH/SOL/RAVE等）
- 可交易高波动标的（类RAVE）
- 允许做级别小一点的交易（30m/15m/5m也可以）
- 结合Price Action Protocol + 唯美MACD两本书的精髓执行

**硬性风控底线（不得违反）** — **2026-04-20 13:25 用户大幅放宽 (比赛冲刺模式)**：
- 任何开仓必须同时挂OCO（SL+TP），不留裸仓
- **单次预期最大亏损 ≤ 账户equity的 20%**（原5%放宽到20%, 当前~$132）
- ~~单仓保证金上限 50 USDT~~ **取消** (2026-04-20)
- ~~保留free USDT ≥ 200U作为缓冲~~ **取消** (2026-04-20)
- **若equity跌破 300 USDT 立即停止新仓**（原650放宽到300）

**仓位sizing原则 (2026-04-20 用户明确)**：
- **不是固定张数**，由AI根据setup质量+R:R+SL距离动态判定
- 比赛追求高收益，可20张、30张甚至更大，只要：
  (a) 预期最大亏损≤20% equity
  (b) R:R≥2:1
  (c) margin不超过available
- BTC示例公式: position_margin = min(available, target_loss / (SL% × leverage))
  例: target_loss $130, SL 0.4%, lever 50x → margin = $650 = ~44张BTC
- 强SL+confluence高 = 大sz; 试探/不确定 = 小sz

**Why**：比赛冲刺期（T-4天），用户追求ROI但更忌讳大幅回撤；APE事件已证明"先小sz试水"的必要性；OCO硬止损是断线保障。

**How to apply**：每个策略循环开始时核查这些约束；开仓前验证保证金、OCO、equity三项；日志必须记录决策理由。

---

## ★高波动标的 SL 规则 (v3.9, 用户多次教学)★

用户多次指出我对RAVE等高波动币SL设得太紧, 导致反复被毛刺洗出:
- 14:35 RAVE 1.437, SL 1.45 (+0.9%) → 秒被洗
- 16:08 RAVE 1.25, SL 1.32 (+5.6%) → 16:25 RAVE 1分钟冲到1.35毛刺打掉 → 实损$10.5

**强制规则 (RAVE/其他24h波动>30%币)**:

1. **SL距离**: 永远 ≥ **20%** (不管用户说小仓)
   - 极端品种(24h波动>50%): ≥30%
   - 对应仓位缩小来控制$亏损: margin = 目标$亏损 / (SL%×leverage)

2. **SL定位**: 用**结构位**, 不是%
   - 做空: SL = 今日大swing high + 0.5%
   - 做多: SL = 今日大swing low - 0.5%
   - 忽略1m小毛刺, 看15m/30m级别结构

3. **绝对禁止**: 在高波动标的上用<10% SL (被洗概率>80%)

4. **替代方法**: 如果结构SL超出$亏损预算 → 缩小仓位, 而不是缩小SL

**Why**: 高波动币每1分钟可以轻松波动5%+, 紧SL就是送钱。
**How to apply**: 每次开RAVE类仓前check 24h high-low%, 大于30%强制执行此规则。

---

## ★v3.14 核心升级 (2026-04-19晚) — 比赛合规 & 关键修复★

用户确认: **Claude (当前session)本身就是AI决策层**。加强AI主导, 修复5个关键逻辑漏洞。

### 1. AI决策层 (Phase 0.1)
- 机械评分/规则 = AI的输入参考
- **最终决策永远由AI(Claude)做出**
- AI可override机械规则, 记录rationale
- 每个GO/SKIP/HOLD决策必须输出structured decision block
- 比赛规则要求"AI综合决策" → 此条为合规核心

### 2. Macro Bear Filter (Phase 0.2, grid保护)
- EDGE/THETA grid -$20教训
- 每cycle check: BTC 1H Supertrend + 30m bars
- Macro bearish时:
  * 拒绝新grid
  * 已有grid pnl<-5%立即stop (不等-10%)
  * grid pnl>0%则trail 30% drawdown
- 解除: BTC 1H UP持续2h + 30m连续2阳

### 3. Leverage Pre-Check (Phase 0.3)
- BTC杠杆错3次教训
- **每次place新仓前强制** `okx swap get-leverage` 验证
- 不匹配则先set再place
- 日志必须出现 "lever=X ✓"
- BTC永远50x, RAVE 5-10x, Grid 10x

### 4. 动态SL算法 (Phase 0.9)
- BTC 15点SL / RAVE 0.9% SL教训
- SL距离 = max(3×1m ATR, 0.3%×price, 2×5m ATR, 结构位距离)
- 按vol调整: >50%→×3, 30-50%→×2, 15-30%→×1.5
- **铁律**: 永远不用 <2% SL (除非super低vol BTC/ETH)
- Trail SL = max(3×1m ATR, 0.5%, 8%×entry for high vol)

### 5. Post-Fill OCO Guardian (Phase 0.95)
- OCO sz=4 vs position=9 裸仓bug
- 每cycle开始check每个position的OCO sz一致性
- 不同步则auto amend
- 无OCO则auto create

**How to apply**: 所有v3.14 phases在每cycle开始必须按顺序跑, 不得跳步。
