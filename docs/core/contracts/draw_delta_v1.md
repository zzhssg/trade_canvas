---
title: Draw Delta Contract v1（统一绘图增量）
status: done
created: 2026-02-02
updated: 2026-02-14
---

# Draw Delta Contract v1（统一绘图增量）

目标：统一 `GET /api/draw/delta` 的输出语义，保证 live/replay 都能用同一增量协议渲染图表。

关联契约：
- `docs/core/contracts/delta_ledger_v1.md`
- `docs/core/contracts/world_state_v1.md`

---

## 1. 约束（必须满足）

1. 仅基于 `closed candle` 推进绘图产物。
2. 读接口只读，不得在读路径写入业务状态。
3. cursor 幂等：同一 cursor 重放不会产生重复图元。
4. 对齐失败时必须 fail-fast：
   - 返回 `409 ledger_out_of_sync:overlay`（overlay 未追平）；
   - 或 `409 ledger_out_of_sync`（world 聚合口径不一致）。

---

## 2. 数据结构

### 2.1 图元增量

```ts
type DrawInstructionPatchItemV1 = {
  version_id: number
  instruction_id: string
  kind: string
  visible_time: number
  definition: Record<string, any>
}
```

语义：
- `instruction_catalog_patch` 只返回 `cursor_version_id` 之后的版本。
- 同一 `instruction_id` 若有新版本，读取端以最新版本覆盖旧版本。

### 2.2 激活集合

```ts
type ActiveInstructionIdsV1 = string[]
```

语义：
- `active_ids` 是当前窗口内“最终应显示”的图元集合。
- 渲染时应以 `active_ids` 作为显示门禁，避免窗口外图元残留。

### 2.3 指标点增量

```ts
type DrawSeriesPointV1 = { time: number; value: number }
type DrawSeriesPointsV1 = Record<string, DrawSeriesPointV1[]>
```

语义：
- 用于指标线逐点增量。
- 当前实现允许返回空对象 `{}`。

### 2.4 cursor

```ts
type DrawCursorV1 = {
  version_id: number
  point_time?: number
}
```

---

## 3. Draw Delta 输出

```ts
type DrawDeltaV1 = {
  schema_version: 1
  series_id: string
  to_candle_id: string | null
  to_candle_time: number | null
  instruction_catalog_patch: DrawInstructionPatchItemV1[]
  active_ids: string[]
  series_points: DrawSeriesPointsV1
  next_cursor: DrawCursorV1
}
```

字段语义：
- `to_candle_id`/`to_candle_time`：本次绘图数据对齐到的闭合 K。
- `next_cursor`：下次增量拉取应使用的游标。

---

## 4. 与实现对齐（2026-02-11）

- 路由：`backend/app/routes/draw.py`
- 读服务：`backend/app/read_models/draw_read_service.py`
- 版本存储：`backend/app/overlay/store.py`
- 完整性检查：`backend/app/overlay/integrity_plugins.py`

关键实现语义：
- `cursor_version_id=0` 首帧会触发完整性校验；
- 读接口固定 strict（只读不写，不触发隐式重算）；
- 发现 overlay 不一致时统一返回 `409 ledger_out_of_sync:overlay`，不在读请求内执行隐式重建；
- 不提供非 strict 兼容口径开关。
