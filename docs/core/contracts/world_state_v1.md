---
title: World State Contract v1（统一世界状态：因子切片 + 绘图状态）
status: draft
created: 2026-02-03
updated: 2026-02-07
---

# World State Contract v1（统一世界状态：因子切片 + 绘图状态）

目标：把 trade_canvas 的“当下世界状态”收敛为一个稳定、可对齐、可复现的统一输出，用于：

- **实盘模式（live）**：一次性加载当前世界状态，然后仅消费增量差分（见 `world_delta_v1`）
- **复盘模式（replay）**：任意时刻 `t` 定点获取世界状态；可由回放包或后端点查投影得到

关联契约：
- 因子切片外壳：`docs/core/contracts/factor_v1.md`
- 绘图增量：`docs/core/contracts/draw_delta_v1.md`
- 回放帧（v1 组合投影）：`docs/core/contracts/replay_frame_v1.md`

---

## 0) 核心不变量（硬门禁）

1) `closed candle` 为权威输入：世界状态只允许对齐到闭合 K（forming 不进入真源）。
2) 对齐：`time.candle_id == factor_slices.candle_id == draw_state.to_candle_id`，否则返回 `ledger_out_of_sync`。
3) `history/head` 语义不变：history=append-only 纯切片；head=可重绘但无未来函数。

---

## 1) Time（对齐主键）

```ts
type WorldTimeV1 = {
  at_time: number        // 请求时刻（unix seconds）
  aligned_time: number   // floor 对齐后的闭合 K candle_time
  candle_id: string      // "{series_id}:{aligned_time}"
}
```

---

## 2) World State（统一世界状态）

```ts
type WorldStateV1 = {
  schema_version: 1
  series_id: string
  time: WorldTimeV1

  // 因子切片（冷+热）；复用现有 `GetFactorSlicesResponseV1` 形状
  factor_slices: {
    schema_version: 1
    series_id: string
    at_time: number
    candle_id: string
    factors: string[]
    snapshots: Record<string, any>
  }

  // 绘图状态：本质上是 “draw delta 在 t 的对齐点视图”
  // v1 允许先用现有 `DrawDeltaV1` 投影表达（active_ids + patch + points）
  draw_state: {
    schema_version: 1
    series_id: string
    to_candle_id: string | null
    to_candle_time: number | null
    active_ids: string[]
    instruction_catalog_patch: any[]
    series_points: Record<string, any[]>
    next_cursor: { version_id: number; point_time?: number | null }
  }
}
```

补充约束（anchor）：
- 当 `factor_slices.snapshots.anchor` 存在时，`history.anchors` 与 `history.switches` 必须是同一可见性过滤结果，并满足 1:1 对齐。

说明：
- `WorldStateV1` 强调“统一输出形状”，不强制后端内部存储实现（可由 ledger/delta ledger 或投影组合得到）。
