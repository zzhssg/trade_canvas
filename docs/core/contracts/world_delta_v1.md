---
title: World Delta Contract v1（统一世界增量差分）
status: draft
created: 2026-02-03
updated: 2026-02-07
---

# World Delta Contract v1（统一世界增量差分）

目标：定义 trade_canvas 的“世界状态差分”最小契约，用于：

- **实盘模式（live）**：每根闭合 K 来一次增量更新（poll/WS），前端只 apply diff
- **复盘模式（replay）**：支持窗口重放（checkpoint + diffs），在前端重建任意 `t` 的世界状态

关联契约：
- `docs/core/contracts/world_state_v1.md`
- `docs/core/contracts/draw_delta_v1.md`
- `docs/core/contracts/delta_ledger_v1.md`（终局真源：world delta 应由 delta ledger 持久化派生）

---

## 0) 核心不变量（硬门禁）

1) append-only：delta 记录只能追加；读取端应可幂等消费（cursor 单调）。
2) 对齐：delta 的 `to_candle_id/to_candle_time` 必须与 market closed 真源一致；不一致返回 `ledger_out_of_sync`。
3) 可复现：同输入重跑，delta 的 `(count,last_candle_id)` 一致。

---

## 1) Cursor

```ts
type WorldCursorV1 = {
  id: number            // 单调递增（cursor）
}
```

---

## 2) Delta Record（每个闭合 K 的变更）

```ts
type WorldDeltaRecordV1 = {
  id: number
  series_id: string

  to_candle_id: string
  to_candle_time: number

  // 绘图增量（catalog patch + active ids + series points delta）
  draw_delta: any

  // v1 兼容投影：当前代码直接返回对齐点的 factor_slices（而非 factor_delta 事件流）
  factor_slices?: any
}
```

说明（2026-02-07 实现口径）：
- 当前 `GET /api/delta/poll` 是兼容投影：增量 cursor 映射到 draw 的 `version_id`。
- 当前实现每次 poll 最多返回 1 条 record（当 cursor 未推进时返回空数组）。
- 终局目标仍是 `delta_ledger_v1` 同源化后提供标准 `factor_delta` 事件语义。

---

## 3) Read API 语义（示意）

### 3.1 `poll(after_id, limit)`（live）

- 输入：`after_id`（上次消费到的最后 id；空/0 表示从头或从 checkpoint）
- 输出：按 id 递增的 `WorldDeltaRecordV1[]` + `next_cursor`
- 兼容实现补充：当前最多返回 1 条（`records.length in {0,1}`）

### 3.2 `get_window(t0..t1)`（replay）

- 输出：覆盖 `[t0..t1]` 的 delta 序列（可选 checkpoint）
