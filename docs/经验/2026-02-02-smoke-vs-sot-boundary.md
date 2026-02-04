---
title: 经验：区分 smoke/demo 与主链路真源（SoT）边界
status: done
created: 2026-02-02
updated: 2026-02-02
---

# 经验：区分 smoke/demo 与主链路真源（SoT）边界

## 场景与目标

在 trade_canvas 早期迭代阶段，经常需要 demo/smoke（快速跑通 UI、跑通 freqtrade backtest），但主链路又要求严格的同源真源（ledger/delta）与可复现性。

目标：
- 允许 demo/smoke 存在，但不污染主链路口径
- 任何“可交易”链路必须强制走 SoT（ledger/delta），并具备 fail-safe

## 可复用做法（检查清单）

**命名与声明**
- [ ] demo/smoke 文件名或类名包含 `Demo`/`Smoke`/`Minimal` 且在头部 docstring 明确“不代表主链路策略口径”
- [ ] 主链路 adapter/strategy 明确标注“只读 SoT，不旁路重算”

**门禁**
- [ ] 新增一个“能失败的”回归：`candle_id mismatch → enter_long/exit_long 全 false`
- [ ] E2E 用例只覆盖主链路策略（消费 ledger/delta），demo/smoke 不作为 E2E 成功标准

**演进路径**
- [ ] 先做统一读口（例如 draw/delta）+ feature flag 切流，再逐步把 SoT（delta ledger）接入
- [ ] 任何临时旁路重算都要被明确隔离（仅限 demo/smoke），并在 plan 中记录替换里程碑

## 关联

- `docs/core/contracts/strategy_v1.md`
- `docs/复盘/2026-02-02-freqtrade-strategy-bypasses-ledger.md`

