# 风控记录 / Risk Log

## 规则（v3.3+）

### R1：单笔亏损上限（25%账户）
每次入场前验证：
  sl_loss = (entry_price - sl_price) × total_sz × 0.01
  sl_loss ≤ equity × 0.25

若超限：缩小sz直到满足，或跳过入场。

### R2：账户最大回撤（10%触发复盘）
每个cycle检查：
  drawdown = (peak_equity - current_equity) / peak_equity
  若 drawdown > 0.10：
    - 停止新开仓
    - 输出[DRAWDOWN ALERT]，列出：回撤幅度、当前持仓、近期操作、原因分析
    - 提出策略改进方案，更新SKILL.md

peak_equity 记录在 state.json，每cycle若current_equity > peak_equity则更新。

## 执行修正记录

### 2026-04-19 K线形态修正
- 问题：⑦K线形态一直报"无数据"
- 原因：未调用 `okx market indicator bull-engulf/three-soldiers` 命令
- 修复：每cycle Phase 2B并行调用，value=1→10分，value=0→0分

### 2026-04-19 杠杆命令修正
- 问题：BTC仓位多次开在100x而非50x
- 原因：`okx swap set-leverage` 命令不存在但不报错
- 修复：改用 `okx swap leverage`，入场前调用 `okx swap get-leverage` 验证

### 2026-04-19 余额列读取修正
- 问题：可用余额长期报错（113U vs 实际610U）
- 原因：读取了第3列(frozen)而非第2列(available)
- 修复：使用 `okx account balance` 完整输出，读取 available 列
