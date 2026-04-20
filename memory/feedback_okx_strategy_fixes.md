---
name: OKX策略执行修正清单
description: OKX compound strategy v3.3执行过程中发现的关键bug和修正方法
type: feedback
originSessionId: 42881390-2a8a-4888-b57d-56fb62215105
---
每次执行OKX复合策略时必须遵守以下修正点：

1. **杠杆命令**：设置杠杆用 `okx swap leverage`（不是set-leverage，后者静默失败）；入场前必须用 `okx swap get-leverage` 验证lever值确为50。

   **★BTC默认杠杆 = 50x (已多次犯错, 必须刻入执行流程)★**
   - BTC-USDT-SWAP 在策略设计中**默认50x isolated**
   - 禁止用10x/20x做BTC, 除非用户明确指示
   - 每次BTC开仓流程:
     (a) `okx swap get-leverage --instId BTC-USDT-SWAP --mgnMode isolated` 验证
     (b) 若不是50 → 先set再开仓 
     (c) 开仓后再次 get-leverage 确认 position显示 lever=50
     (d) 日志明确写"BTC open at 50x ✓"
   - 犯错历史: 2026-04-19至少3次用10x开BTC, 每次被用户纠正

   **其他标的默认杠杆**:
   - RAVE: 10x isolated
   - 网格/Grid标的: 10x isolated
   - 动态扫描的单边标的: 5x isolated (v3.7/3.8)

2. **余额读取**：`okx account balance` 输出3列：equity / available / frozen。取第2列(available)作为free_usdt，不是第3列。

3. **K线形态**：每cycle Phase 2B必须并行调用 `okx market indicator bull-engulf BTC-USDT-SWAP --bar 5m` 和 `okx market indicator three-soldiers BTC-USDT-SWAP --bar 5m`，value=1→10分，value=0→0分，不能写"无数据"。

4. **网格命令**：`okx bot grid details` 和 `okx bot grid orders` 必须带 `--algoOrdType contract_grid`。

5. **平仓命令**：`okx swap close` 需要 `--mgnMode` 参数，如 `--mgnMode isolated` 或 `--mgnMode cross`。

6. **★OCO size 同步★ (新加, 2026-04-19教训)**:
   每次加仓(分层挂单filled / 手动加market)后, **必须立即**:
   - `okx swap algo amend --algoId {id} --newSz {total_position_sz}`
   - 否则OCO只覆盖原始sz, 新增合约**无止损保护** = 隐性爆仓风险
   - 例: 原OCO sz=4, 加仓后position=9 → 剩余5张无OCO保护

8. **★★ Grid stopType真实行为 (2026-04-19 严重教训) ★★**:

   **错误**: 用 `okx bot grid stop --stopType 2` 后, 看 `okx account positions` 没EDGE → 以为已平仓
   **事实**: grid仓位**不显示**在标准 account positions 中! Grid有自己的仓位池
   **后果**: EDGE/THETA grids在"停止"后继续MTM亏损, 从-28% → -38% 实时扩大
   **用户不得不手动平仓** 才真正释放margin

   **正确理解**:
   - Grid stopType=2 **不一定**立即close positions (行为因OKX环境而异)
   - `no_close_position` state **不是"已平仓"**, 是"algo停了但仓位状态不明"
   - **必须通过多重检查验证**:
     a. `okx bot grid details` 的 pnlRatio 若仍在变化 → 仓位仍open
     b. `okx swap close --instId X --mgnMode isolated` 强制市价平
     c. 用OKX网页UI看"bot grid position"专区
     d. 账户frozen margin若没释放 → 仓位仍持有

   **铁律 (v3.14)**:
   - Grid stop后**永远**再额外执行 `okx swap close --instId {symbol} --mgnMode isolated`
   - 或直接用 `okx bot grid stop --stopType 3` (强制市价平仓版本, 如支持)
   - 平仓后等60秒再查pnlRatio, 若还在变 = 未平完, 需手动close
   - frozen margin释放 = 确实平了

---

7. **★Trailing SL距离规则★ (2026-04-19 18:57 教训)**:
   Trailing SL 不能太紧 (被normal chop打出)：
   - **最小距离** = 当前价 ± 1m ATR × 3
   - BTC 1m ATR ~30点 → SL至少+90点远
   - 若用结构trail: SL = 最近明显swing高点 + 0.2-0.3% buffer
   - **禁止**: Trail SL设在当前价±50点以内 (必被洗)
   
   本次教训: BTC SL 75200, current 75185, 距离仅15点
   → 1m normal bounce到75200触发 → 9张short被洗出
   → 正确应设在75300+ (100+点buffer)

**Why:** 上述都是在实盘执行中发现的静默失败或列误读，导致100x杠杆爆仓风险、余额判断错误等严重问题。
**How to apply:** 每次执行策略循环时按此清单核查，尤其是入场操作前。
