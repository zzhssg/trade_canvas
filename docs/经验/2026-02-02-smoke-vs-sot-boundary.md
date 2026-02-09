---
title: "区分 smoke/demo 与主链路真源边界（防止策略旁路重算）"
status: done
created: 2026-02-02
updated: 2026-02-09
---

# 区分 smoke/demo 与主链路真源边界（防止策略旁路重算）

## 问题背景

仓库内存在用于 freqtrade smoke 的策略实现 `Strategy/TradeCanvasMinimalStrategy.py`，其在 `populate_indicators()` 内直接用 rolling 计算 `sma_fast/sma_slow` 并产生入场/出场信号。这等价于"策略侧旁路重算因子"，与 `docs/core/contracts/strategy_v1.md` 中"策略消费同源快照、禁止直接重算因子"的约束冲突。

当主链路开始以 ledger/delta 作为真源时，策略侧旁路重算会产生"画对了但算错了 / 链路断了"的漂移风险。

## 根因

1. demo/smoke 策略与主链路策略契约未做明显隔离（命名/文档/门禁均不足）。
2. 缺少一个"策略必须读取 ledger/delta"的自动化回归（例如 candle_id 不一致时 enter_long 全 false）。

## 解法

**命名与声明**
- demo/smoke 文件名或类名包含 `Demo`/`Smoke`/`Minimal` 且在头部 docstring 明确"不代表主链路策略口径"。
- 主链路 adapter/strategy 明确标注"只读 SoT，不旁路重算"。

**门禁**
- 新增一个"能失败的"回归：`candle_id mismatch -> enter_long/exit_long 全 false`。
- E2E 用例只覆盖主链路策略（消费 ledger/delta），demo/smoke 不作为 E2E 成功标准。

**演进路径**
- 先做统一读口（draw/delta）+ feature flag 切流，再逐步把 SoT（delta ledger）接入。
- 任何临时旁路重算都要被明确隔离（仅限 demo/smoke），并在 plan 中记录替换里程碑。

## 为什么有效

- 允许 demo/smoke 存在但不污染主链路口径，兼顾快速验证与真源严格性。
- 自动化回归把"旁路重算"变成可检测的违规，而不是隐式漂移。

## 检查清单

**开发前**
- [ ] demo/smoke 用途必须显式标注（文件头/命名包含 `demo`/`smoke`），并声明"不代表主链路策略口径"。
- [ ] 任何"策略可交易"链路必须先写 fail-safe：`candle_id`/`at_time` 不一致 -> 拒绝信号。

**开发中**
- [ ] 策略逻辑只读取 `StrategyInputV1.snapshots`（或 delta ledger 派生输入），不得引入 rolling 旁路重算。
- [ ] 需要指标线时，只允许从 draw/delta 的 `series_points` 或 factor ledger 派生（同源）。

**验收时**
- [ ] 至少一条回归：`candle_id mismatch -> enter_long/exit_long 全 false`（pytest）。
- [ ] `bash docs/scripts/doc_audit.sh` 确保文档一致性。

## 关联

- `Strategy/TradeCanvasMinimalStrategy.py`
- `docs/core/contracts/strategy_v1.md`
- `docs/plan/2026-02-02-factor-engine-graph-ledgers-v1.md`
