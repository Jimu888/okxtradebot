# OKX策略 — 重启后恢复指令

**最后快照**: 2026-04-19 02:55

## 复制粘贴这段给新session，立刻接上策略

```
你是OKX复合策略v3.6的执行者。我刚重启了session，你需要立即接上策略执行。

**立刻执行以下3步**：

1. 读取当前状态：
   - /Users/jimu/okx-compound-strategy/runner/state.json (当前仓位/grids/Gemma4分析)
   - /Users/jimu/okx-compound-strategy/runner/strategy_log.md (最近决策日志)
   - /Users/jimu/okx-compound-strategy/skills/okx-compound-strategy/SKILL.md (策略规则v3.6)

2. 快速对账：
   - okx account balance (确认USDT余额)
   - okx account positions (应无持仓)
   - okx swap algo orders (应无algo)
   - okx bot grid orders --algoOrdType contract_grid (应有3个grids: EDGE/THETA/APE)

3. 确认就绪后，等我的进一步指令（我可能从Telegram发消息）。
   比赛截止2026-04-23 16:00，剩T-4天13小时。

所有CLI命令前缀：
NODE_OPTIONS="--require /Users/jimu/.okx/proxy-inject.cjs" PATH="/opt/homebrew/opt/node@18/bin:$PATH"

确认状态后，简短报告equity/grids pnl，然后待命。
```

## 当前快照（作为参考）

**账户**: 692.29 USDT (peak 728, -4.9%)
- Free: 527.82 USDT
- Frozen: 164.47 USDT（grids margin）

**持仓**: 无（BTC已止损-34U, RAVE空单TP+8.25U）

**Algo订单**: 无（RAVE OCO已消费）

**Grids**:
| 网格 | algoId | pnl |
|------|--------|-----|
| EDGE-USDT-SWAP | 3490065356448776192 | +3.32% |
| THETA-USDT-SWAP | 3490161303400898560 | +5.63% |
| APE-USDT-SWAP | 3490866047169748992 | 0% (新) |

**关键教训记录**（不要再犯）:
- APE ctVal=0.1（而EDGE=10），sz数字含义不同
- Contract grid的margin保留比notional计算高很多
- 部署新grid时先用小sz测试，再根据frozen变化调整
- OKX CLI --bar 6H/12H参数可能返回对调的数据，必须以timestamps间隔验证

**市场判断（Gemma4最新）**:
- DIRECTION: SHORT, CONFIDENCE: MEDIUM
- 4H MACD零轴上方死叉持续
- 1H Supertrend DOWN, ADX强化
- support_1=73800, resistance_1=78000

**Telegram状态**:
- Token已配置 ~/.claude/channels/telegram/.env
- 策略: allowlist（已锁定）
- 授权ID: 7762516107（用户）
- 重启时用命令: `claude --channels plugin:telegram@claude-plugins-official`
