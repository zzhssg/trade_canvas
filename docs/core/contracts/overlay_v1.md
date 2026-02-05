---
title: Overlay / Plot Contract v1（绘图数据结构）
status: deprecated
created: 2026-02-02
updated: 2026-02-05
---

# Overlay / Plot Contract v1（绘图数据结构）

目标：让 **后端增量产出** 的绘图数据（指标线/标记）能在 K 线收线后低延时展示，并且支持“按 cursor 增量拉取”，避免全量重算/全量回传。

> 说明：本契约为 v0 过渡形态，已于 2026-02-05 标记 deprecated。统一的“绘图指令底座”以 `docs/core/contracts/draw_delta_v1.md` 为准；`/api/plot/delta` 与 `/api/overlay/delta` 已删除，读口收敛到 `GET /api/draw/delta`。

本契约“批判性继承”自 `trade_system` 的关键口径：
- `closed candle` 为权威输入；绘图数据只随 `CandleClosed` 增量推进（append-only）。
- 读路径应优先走“已落盘产物”（避免临时全量重算导致漂移/抖动）。
- cursor 语义明确：重复拉取幂等，单调推进。

> v1 先覆盖最小形态：**line points** + **overlay events**。复杂图元（线段/区域/箱体）后续再扩展。

---

## 1. Line Series（指标线点）

```ts
type PlotLinePointV1 = {
  time: number   // unix seconds (candle open time)
  value: number
}

type PlotLinesV1 = Record<string /* feature_key */, PlotLinePointV1[]>
```

约束：
- 每根收线最多追加 1 个点（同一 `feature_key`）。
- `time` 必须对齐到对应 `candle_time`（不得用 idx 作为主键）。

---

## 2. Overlay Events（离散标记/事件）

```ts
type OverlayEventV1 = {
  id: number                 // 单调递增（用于 cursor）
  kind: string               // 例如 "signal.entry"
  candle_id: string
  candle_time: number
  payload: Record<string, any> // JSON 友好
}
```

约束：
- append-only（允许重复写入但应可幂等去重）。
- `payload.time`（若存在）应等于 `candle_time`。

---

## 3. Plot Delta（增量读取）

```ts
type PlotCursorV1 = {
  candle_time?: number
  overlay_event_id?: number
}

type PlotDeltaV1 = {
  schema_version: 1
  symbol: string
  timeframe: string

  // 当前已对齐的最新收线
  to_candle_id: string
  to_candle_time: number

  // 仅返回 cursor 之后的增量
  lines: PlotLinesV1
  overlay_events: OverlayEventV1[]

  next_cursor: PlotCursorV1
}
```

硬约束：
- 若 `latest_candle_id != latest_ledger.candle_id`，必须 fail-safe（拒绝输出绘图增量），避免前端展示“未对齐的证据”。
