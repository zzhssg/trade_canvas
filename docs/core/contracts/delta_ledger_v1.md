---
title: Delta Ledger Contract v1（二级增量账本）
status: draft
created: 2026-02-02
updated: 2026-02-09
---

# Delta Ledger Contract v1（二级增量账本）

目标：定义 trade_canvas 的 **二级增量账本**（delta ledger）最小契约，用于：

- **回放友好**：给定窗口/游标可重放增量，复现任意时刻的“绘图/信号/事件流”。
- **实盘友好**：live poll/WS 只拉增量，不做全量重算。
- **同源**：delta 必须从因子真源账本（cold+hot）派生，避免“绘图链路/策略链路各自重算导致漂移”。

关联契约：
- 因子真源账本：`docs/core/contracts/factor_ledger_v1.md`
- 绘图增量输出：`docs/core/contracts/draw_delta_v1.md`
- 策略输入/输出：`docs/core/contracts/strategy_v1.md`

## 1. 记录模型（抽象）

```ts
type DeltaRecordV1 = {
  id: number                 // 单调递增（cursor）
  series_id: string
  candle_id: string
  candle_time: number

  // 该 candle 引入的增量（均为 append-only 视角）
  factor_history_events?: Array<Record<string, any>>
  factor_head_snapshots?: Array<Record<string, any>>
  overlay_events?: Array<Record<string, any>>
  indicator_points?: Array<Record<string, any>>
  strategy_outputs?: Array<Record<string, any>>
}
```

约束：
- append-only：只允许追加新 `DeltaRecordV1`；同一 `candle_time` 的尾部修订允许追加新版本（由上层以 `seq` 或新 `id` 表达），读取端必须以“最新版本”视角消费。
- 对齐：`candle_id/candle_time` 必须与 CandleStore 的 `closed` 真源一致；若不一致必须 fail-safe（拒绝对外提供 delta）。

## 2. 读 API（语义）

### 2.1 `poll(after_id, limit)`（live）

- 输入：`after_id`（上次消费到的最后 id；空表示从头/从某个 checkpoint）
- 输出：按 id 递增的 `DeltaRecordV1[]` + `next_cursor`（最大 id）

### 2.2 `get_window(t0..t1)`（replay）

- 输出：覆盖 `[t0..t1]` 的 delta 序列（可选包含 checkpoint），并保证可重建：
  - overlay 增量（markers/lines）
  - strategy 信号事件流（entries/exits）

## 3. 最小门禁（必须可自动化）

1) 同输入同输出：同一份 `CandleClosed` 输入在新 DB 重跑，delta 的 `(count,last_candle_id)` 一致。
2) 幂等：重复 ingest 同一段 candles，不应产生重复 delta（或必须可被 cursor 幂等消费，不影响重建结果）。
3) fail-safe：当 `candle_id` 不一致（人为篡改或不同步）时：
   - 读 delta 必须返回错误（ledger_out_of_sync）
   - 策略必须拒绝出信号（enter/exit 全部为 false）

