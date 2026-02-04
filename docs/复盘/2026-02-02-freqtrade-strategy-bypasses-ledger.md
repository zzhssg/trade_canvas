---
title: 复盘：freqtrade 策略旁路重算（违背同源 ledger 约束）
status: done
created: 2026-02-02
updated: 2026-02-02
---

# 复盘：freqtrade 策略旁路重算（违背同源 ledger 约束）

## 背景

仓库内存在一个用于 freqtrade smoke 的策略实现：

- `Strategy/TradeCanvasMinimalStrategy.py`

同时，本仓的主链路成功标准强调：

- `closed candle` 驱动 → 因子/策略产物同源（ledger/delta）
- 策略不得旁路重算因子（避免 replay/live/overlay 漂移）

相关契约：
- `docs/core/contracts/strategy_v1.md`
- `docs/plan/2026-02-02-factor-engine-graph-ledgers-v1.md`

## 具体问题（可复现的现象/证据）

`TradeCanvasMinimalStrategy` 在 `populate_indicators()` 内直接用 rolling 计算 `sma_fast/sma_slow`，并以此产生入场/出场信号：

- 这等价于“策略侧旁路重算因子”
- 与 `docs/core/contracts/strategy_v1.md` 中“策略消费同源快照、禁止直接重算因子”的约束冲突

## 影响与代价

- 风险：当主链路开始以 ledger/delta 作为真源时，策略侧旁路重算会产生“画对了但算错了 / 链路断了”的漂移风险。
- 代价：后续接入真正的 freqtrade adapter 时，需要同时改策略实现、补 fail-safe、补回归测试与 E2E 门禁。

## 根因（1–3 条）

1) demo/smoke 策略与主链路策略契约未做明显隔离（命名/文档/门禁均不足）。
2) 缺少一个“策略必须读取 ledger/delta”的自动化回归（例如 candle_id 不一致时 enter_long 全 false）。

## 如何避免（检查清单）

**开发前**
- [ ] demo/smoke 用途必须显式标注（文件头/README/命名包含 `demo`/`smoke`），并在 plan 中声明“不代表主链路策略口径”。
- [ ] 任何“策略可交易”链路必须先写 fail-safe：`candle_id`/`at_time` 不一致 → 拒绝信号。

**开发中**
- [ ] 策略逻辑只读取 `StrategyInputV1.snapshots`（或 delta ledger 派生输入），不得引入 rolling 旁路重算。
- [ ] 需要指标线时，只允许从 draw/delta 的 `series_points` 或 factor ledger 派生（同源）。

**验收时**
- [ ] 至少一条回归：`candle_id mismatch → enter_long/exit_long 全 false`（pytest）
- [ ] E2E：同一份 `CandleClosed` 输入重跑，策略输出与 draw delta 的对齐点一致（`to_candle_id` / `at_time`）

## 关联与证据

- 关键文件：
  - `Strategy/TradeCanvasMinimalStrategy.py`
  - `docs/core/contracts/strategy_v1.md`
  - `docs/plan/2026-02-02-factor-engine-graph-ledgers-v1.md`
- 验证命令（文档一致性）：
  - `bash docs/scripts/doc_audit.sh`

