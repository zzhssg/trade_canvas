---
title: Draw Delta Contract v1（统一绘图指令底座）
status: draft
created: 2026-02-02
updated: 2026-02-02
---

# Draw Delta Contract v1（统一绘图指令底座）

目标：把 trade_canvas 的“绘图/指标/标记”统一为一份 **可 cursor 增量拉取**、**同源可复现** 的输出，用于：

- 前端图表（lightweight-charts）增量渲染
- replay/live 同口径回放
- 未来接入 delta ledger（`docs/core/contracts/delta_ledger_v1.md`）

约束（硬门禁）：
- **closed candle 为权威输入**：所有绘图产物只随 `CandleClosed` 推进（append-only 视角）。
- **读路径只读**：绘图读 API 不得触发隐式重算/写入。
- **cursor 幂等**：重复拉取同一 cursor 的结果可重复 apply（不会造成“越拉越多的重复图元”）。
- **fail-safe**：当发现 `candle_id` 不一致（或上游 ledger/out-of-sync）时，必须拒绝输出（返回 `ledger_out_of_sync`）。

关联契约：
- Overlay 指令（历史遗留/过渡）：`docs/core/contracts/overlay_v1.md`
- Delta ledger（终局同源增量）：`docs/core/contracts/delta_ledger_v1.md`

---

## 实现状态（v0→v1 过渡说明）

本契约是“统一底座”的 v1 目标形态；当前仓库内存在一条过渡实现用于“先统一读口与前端 apply 引擎”：

- 后端读口：`GET /api/draw/delta`（v0 兼容投影）
  - `instruction_catalog_patch/active_ids`：等价复用 `GET /api/overlay/delta`
  - `series_points`：当前返回空 `{}`（待接入指标点真源后补齐增量）
  - **fail-safe**：v0 兼容投影当前不强制执行（待接入 factor/delta ledger 的 candle_id 对齐门禁后补齐）
- 前端切流：通过 `VITE_ENABLE_DRAW_DELTA=1` 切换到 `/api/draw/delta`（默认关闭，便于回滚）

结论：在 v1 门禁落地前，`/api/draw/delta` 主要用于“统一协议形状 + 小步切流”，不要把它当作已完全满足本契约所有硬门禁的终局真源。

---

## 1) Draw Instruction Patch（图元定义增量）

复用 v0 overlay 的“版本化 catalog patch”语义：按 `version_id` 单调递增，只追加，不回写。

```ts
type DrawInstructionPatchItemV1 = {
  version_id: number
  instruction_id: string          // 稳定 id（如 pivot.major:time:dir:window / pen.confirmed）
  kind: string                    // marker | polyline | box | ...
  visible_time: number            // 该版本何时可见（<= 当前 to_candle_time 才应激活）
  definition: Record<string, any> // JSON 友好，具体由 kind 决定
}
```

读取端语义：
- `instruction_catalog_patch` 只包含 `cursor_version_id` 之后的新增版本。
- 同一 `instruction_id` 的新版本覆盖旧版本（读取端以“最新版本”视角渲染）。

---

## 2) Active IDs（窗口内激活集合）

```ts
type ActiveInstructionIdsV1 = string[] // 排序后的 instruction_id 集合
```

语义：
- `active_ids` 表示在当前 tail window 内“应当被绘制”的图元集合。
- 读取端应以 `active_ids` 做“显示/隐藏”的最终门禁（避免窗口外的旧图元残留）。

---

## 3) Series Points（指标线点增量）

用于轻量指标线（SMA/EMA/RSI 等）逐根追加点，避免把线作为“大 polyline”反复全量传输。

```ts
type DrawSeriesPointV1 = { time: number; value: number }
type DrawSeriesPointsV1 = Record<string /* feature_key */, DrawSeriesPointV1[]>
```

约束：
- 每根收线最多追加 1 个点（同一 `feature_key`）。
- `time` 必须对齐到 candle open time（unix seconds）。

---

## 4) Cursor（增量读取游标）

```ts
type DrawCursorV1 = {
  version_id: number        // instruction catalog 的增量 cursor
  point_time?: number       // 可选：series points 增量 cursor（按 time 单调）
}
```

约束：
- cursor 单调推进；重复使用同一 cursor 拉取结果应幂等。

---

## 5) Draw Delta（统一输出）

```ts
type DrawDeltaV1 = {
  schema_version: 1
  series_id: string

  // 当前已对齐的最新收线（绘图产物的真源对齐点）
  to_candle_id: string | null
  to_candle_time: number | null

  // 指令定义增量（cursor 之后）
  instruction_catalog_patch: DrawInstructionPatchItemV1[]
  // 当前窗口内激活集合
  active_ids: string[]

  // 指标线点增量（cursor 之后）
  series_points: DrawSeriesPointsV1

  next_cursor: DrawCursorV1
}
```
