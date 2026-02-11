---
title: Replay Frame Contract v1（回放帧：因子切片 + 绘图指令）
status: done
created: 2026-02-02
updated: 2026-02-11
---

# Replay Frame Contract v1（回放帧：因子切片 + 绘图指令）

目标：定义 replay 回放在 **t 时刻** 的统一输出形状，使前端能用“同一份输入（closed candle）”稳定回放：

- **因子数据切片（冷 + 热）**：用于侧边栏/调试面板/后续策略对拍。
- **指令绘图（draw delta）**：用于 lightweight-charts 增量叠加（markers/lines/series points）。

设计取舍：
- 本契约聚焦“t 时刻输出是什么、如何对齐、如何 fail-safe”，不规定后端具体存储（SQLite/jsonl/内存均可）。
- v1 允许“回放帧”通过现有读口组合投影（例如 `factor/slices + draw/delta`），但必须满足对齐门禁与可复现性。

关联契约：
- K 线坐标与主键：`docs/core/market-kline-sync.md`
- 因子真源账本（冷热）：`docs/core/contracts/factor_ledger_v1.md`
- Draw 增量输出：`docs/core/contracts/draw_delta_v1.md`
- 二级增量账本（终局真源）：`docs/core/contracts/delta_ledger_v1.md`

---

## 0) 核心不变量（硬门禁）

1) **closed candle 为权威输入**：`t` 必须对齐到 `floor_time(series_id, at_time)` 的闭合 K（见 `market-kline-sync`）。
2) **同输入同输出**：同一段 `CandleClosed[]` 在新环境重跑，给定同一 `t`，`ReplayFrameV1` 的关键字段（`candle_id / factor snapshots / draw cursor 之后的输出`）必须一致。
3) **forming 只用于显示**：允许提供“热（hot）”视图，但它：
   - 不得写入 cold history
   - 不得改变策略 ledger 的信号口径（策略默认只读 cold 对齐点）
4) **fail-safe 对齐**：当发现任一链路对齐点不一致时，必须拒绝输出（返回 `ledger_out_of_sync`）：
   - `market.closed_head_time`
   - `factor_ledger.series_head_time`
   - `draw_delta.to_candle_time`

---

## 1) 时间点与主键

```ts
type ReplayTimeV1 = {
  at_time: number        // 请求时刻（unix seconds）
  aligned_time: number   // floor 对齐后的闭合 K candle_time
  candle_id: string      // "{series_id}:{aligned_time}"
}
```

补充约束（anchor）：
- `factor_slices.snapshots.anchor.history.anchors` 与 `history.switches` 必须在 `t` 时刻满足 1:1 对齐，避免“末态倒推历史”。

约束：
- `aligned_time` 必须存在；否则返回 `no_data`（该 series 尚无任何闭合 K）。

---

## 2) 因子输出（冷 + 热切片）

v1 复用现有 slice 形状（见 `FactorSliceV1` / `GetFactorSlicesResponseV1`），并把它作为 replay 的“t 时刻快照输出”：

```ts
type ReplayFactorSlicesV1 = {
  schema_version: 1
  series_id: string
  at_time: number         // = aligned_time
  candle_id: string
  factors: string[]
  snapshots: Record<string /* factor_name */, {
    schema_version: 1
    history: Record<string, any>   // cold（<=t 的 append-only 事件切片）
    head: Record<string, any>      // hot（<=t 的快照/视图；不改变 cold 口径）
    meta: { series_id: string; at_time: number; candle_id: string; factor_name: string; epoch: number }
  }>
}
```

说明：
- “冷（cold）”来自 `FactorHistoryEventV1` 的纯切片语义（`candle_time <= t`），禁止隐式重算。
- “热（hot）”允许表达“尾部预览/中间态”，但必须是 `<=t` 的派生视图，并且可被清晰标记为 `head`（不与 cold 混用）。

---

## 3) 绘图输出（draw delta）

复用 `DrawDeltaV1`，但 replay 必须能以 `t` 为上限生成一致的增量视图：

```ts
type ReplayDrawDeltaV1 = DrawDeltaV1 & {
  // 约束：to_candle_time 必须等于 aligned_time
}
```

约束：
- replay 下的 `draw_delta.to_candle_time` 必须等于 `aligned_time`（不能默认为 store head）。
- cursor 幂等：重复请求相同 cursor 的结果可重复 apply。

---

## 4) 回放帧（统一输出）

```ts
type ReplayFrameV1 = {
  schema_version: 1
  series_id: string

  time: ReplayTimeV1

  // 因子切片（冷+热）
  factor_slices: ReplayFactorSlicesV1

  // 绘图指令（增量）
  draw_delta: ReplayDrawDeltaV1
}
```

实现备注（2026-02-09）：
- 当前后端对外读口是 `WorldStateV1`（`GET /api/frame/live` 与 `GET /api/frame/at_time`），字段名已统一为 `draw_delta`。

---

## 5) 最小化增删（k 线播放的工程约束）

说明：lightweight-charts 的数据写入更偏向“只追加/更新末尾”，并不擅长频繁删除头部数据。
因此 replay 的“最小化增删”是一个 **工程层** 约束（前端/adapter 的 apply 策略），不强制进入本契约字段。

推荐策略（非强制）：
- 正向逐根播放：对 candle 序列使用 `series.update(bar)`（追加或更新最后一根）。
- `seek/rewind/jump`：只在发生非相邻跳转时触发一次 `setData(window)` 进行 rebase（一次性重设窗口）。
- 窗口裁剪：当本地缓存超过阈值（例如 5000 根）时再触发 rebase 到“最近 N 根”，避免每步删除。

---

## 6) 最小门禁（必须可自动化）

1) **对齐门禁**：`ReplayFrameV1.time.candle_id == factor_slices.candle_id == draw_delta.to_candle_id`，否则返回 `ledger_out_of_sync`。
2) **可复现**：相同 fixtures 输入，固定 `t` 取帧的结果一致（至少 `(candle_id, factors, active_ids, next_cursor.version_id)` 一致）。
3) **幂等**：同 cursor 的 `draw_delta` 可重复 apply，不产生重复图元。
