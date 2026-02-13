---
title: Factor SDK Contract v1（因子开发 SDK）
status: done
created: 2026-02-07
updated: 2026-02-13
---

# Factor SDK Contract v1（因子开发 SDK）

目标：为 trade_canvas 的因子开发提供统一 SDK 约定，使因子实现与存储/绘图/策略/回放 **同源可复现**。

非目标：不在本契约中规定具体算法细节（如 pivot/pen/zhongshu 计算），也不绑定存储实现（SQLite/file）。

关联真源：
- 因子外壳与冷热语义：`docs/core/contracts/factor_v1.md`
- 因子拓扑与调度：`docs/core/contracts/factor_graph_v1.md`
- 因子插件注册：`docs/core/contracts/factor_plugin_v1.md`
- 因子真源账本：`docs/core/contracts/factor_ledger_v1.md`
- 二级增量账本：`docs/core/contracts/delta_ledger_v1.md`
- 策略边界：`docs/core/contracts/strategy_v1.md`
- 当前模块化落地：`docs/core/factor-modular-architecture.md`

---

## 1) 核心不变量（SDK 必须保证）

1. **closed candle 为唯一输入**：SDK 只接受 `CandleClosed`，forming 不进入引擎。
2. **seed ≡ incremental**：全量 seed 结果与逐根 `apply_closed` 结果一致。
3. **history append-only**：历史事件流只能追加；切片只过滤，不重算。
4. **head 可重绘但可追溯**：同一 `candle_time` 的 head 变化必须以 `seq+1` 的新记录追加表达。
5. **fail-safe**：当 `series_head_time < aligned_time` 或 `candle_id` 不一致时，读路径必须拒绝输出。

---

## 2) SDK 结构（建议的最小接口）

### 2.1 FactorSpec（静态描述）

复用 `FactorSpecV1`（见 `factor_v1.md`），SDK 只要求补齐：
- `factor_name`（稳定、短名）
- `depends_on`（拓扑依赖）
- `logic_hash`（可复现版本）

### 2.2 FactorContext（运行时上下文）

```ts
type FactorContextV1 = {
  series_id: string
  candle_id: string
  candle_time: number
  candle: CandleClosed
  deps_snapshot: Record<string, FactorSliceV1>
  params: Record<string, any>
  epoch: number
}
```

约束：
- `deps_snapshot[*].meta.at_time == candle_time`，否则必须 fail-safe。
- 不允许因子直接访问上游计算接口（禁止回调 slice）。

### 2.3 FactorApplyResult（写路径输出）

```ts
type FactorHistoryEventV1 = {
  factor_name: string
  candle_time: number
  kind: string
  event_key: string
  payload: Record<string, any>
}

type FactorHeadSnapshotV1 = {
  factor_name: string
  candle_time: number
  head: Record<string, any>
  seq: number
}

type FactorApplyResultV1 = {
  history_events?: FactorHistoryEventV1[]
  head_snapshot?: FactorHeadSnapshotV1 | null
}
```

约束：
- `event_key` 必须稳定可重放（同一事件多次 ingest 不应生成重复语义）。
- `head_snapshot.seq` 只允许递增；同 `candle_time` 的变更必须新建记录。

---

## 3) 读路径（Slice Builder）

SDK 必须提供“只读 ledger”的 slice 构造：

```ts
type FactorSliceBuilderV1 = {
  slice_history(factor_name, at_time): Record<string, any>
  get_head_at_or_before(factor_name, at_time): Record<string, any> | null
}
```

规则：
- `slice_history` 只做过滤/截断，不重算。
- `get_head_at_or_before` 返回 `candle_time<=at_time` 的最新 head 记录（同 `candle_time` 取最大 `seq`）。

---

## 4) 存储绑定（最低要求）

SDK 不绑定具体存储，但必须满足下列语义：

- `FactorHistoryEventV1` → 冷账本（append-only）
  - 推荐唯一约束：`UNIQUE(series_id, factor_name, event_key)`
- `FactorHeadSnapshotV1` → 热账本（append-only）
  - 推荐唯一约束：`UNIQUE(series_id, factor_name, candle_time, seq)`
- `series_head_time` → 进度指针（可 upsert）
  - 读路径必须以其作为 fail-safe 门禁。

---

## 5) 与绘图/策略/回放的关系

- **绘图**：优先从 history/head 派生 overlay/draw delta；禁止在读路径隐式重算。
- **策略**：策略只读因子快照（ledger view），不得直接重算因子。
- **回放**：Replay Frame 只组合 `factor_slices + draw_delta`，且必须对齐到同一 `candle_id`。

---

## 6) 新因子开发最小清单（SDK 验收）

1. 声明 `FactorSpec`（name/depends_on/logic_hash）。
2. 实现 `apply_closed(ctx)`，产出 history/head。
3. 保证 `event_key` 幂等（重复 ingest 不产生重复语义）。
4. 推荐先跑脚手架命令：`python3 scripts/new_factor_scaffold.py --factor <name> --depends-on <deps>`。
5. 在 `backend/app/factor/processor_<name>.py` 填充写路径插件逻辑（至少 `run_tick`；按需实现 `bootstrap_from_history`/`build_head_snapshot`）。
6. 在 `backend/app/factor/bundles/<name>.py` 填充 slice 插件逻辑并导出 `build_bundle()`。
7. 在 `XxxSlicePlugin.bucket_specs` 注册 slice 事件桶映射（`event_kind -> bucket_name`，单点维护）。
8. （按需）若该因子需要直接输出策略列/信号，补 `backend/app/freqtrade/signal_strategies/` 插件而非改 adapter 主流程。
9. （按需）若该因子引入 overlay 与 factor 快照一致性约束，补 `backend/app/overlay/integrity_plugins.py` 插件而非改 `draw_routes` 主流程。
10. 补齐测试：
   - `seed ≡ incremental`
   - 重复 ingest 幂等
   - `series_head_time < aligned` 时读路径 fail-safe

---

## 7) 示例骨架（伪代码）

```ts
class PivotFactor implements FactorV1 {
  spec = { factor_name: "pivot", depends_on: [], logic_hash: "pivot:v1" }

  apply_closed(ctx: FactorContextV1): FactorApplyResultV1 {
    const majors = compute_major_pivots(...)
    const events = majors.map(m => ({
      factor_name: "pivot",
      candle_time: m.visible_time,
      kind: "pivot.major",
      event_key: `major:${m.pivot_time}:${m.direction}:${m.window}`,
      payload: {...m}
    }))
    const head = { minor: compute_minor_pivots(...)}
    return { history_events: events, head_snapshot: { factor_name: "pivot", candle_time: ctx.candle_time, head, seq: 0 } }
  }
}
```

> 说明：head 的 `seq` 由存储层控制递增；示例中用 `0` 表示首次写入。
