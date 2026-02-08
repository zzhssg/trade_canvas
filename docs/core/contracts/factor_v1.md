---
title: Factor Contract v1（因子类数据结构）
status: draft
created: 2026-02-02
updated: 2026-02-02
---

# Factor Contract v1（因子类数据结构）

目标：为 trade_canvas 的“因子引擎/策略/绘图”提供一套 **最小且可落地** 的因子数据结构契约。

本契约“批判性继承”自 `trade_system`（只继承术语/外壳/不变量，不继承实现与工程负债）：
- 因子输出统一外壳：`{"history","head","meta"}`（便于 ledger / slice / explain 同源）。
- `candle_time`（Unix seconds）为跨窗口稳定主键；`idx` 只允许作为窗口内派生编号。
- `history` 必须 append-only（以事件流表达）；`head` 允许短窗重算/重绘，但必须无未来函数。
- `seed ≡ incremental`：全量 seed 的结果应等价于逐根 `apply_closed()`。

关联真源（坐标系/主键）：`docs/core/market-kline-sync.md`。

---

## 0. 核心名词

- `series_id`：一条 K 线序列的稳定标识（建议包含 exchange/market/symbol/timeframe）。
- `epoch`：历史修订强失效代号（MVP 可先固定为 `0`，但字段保留）。
- `candle_time`：K 线开盘时间（Unix seconds，按 timeframe 边界对齐）。
- `at_time`：因子对外“可见”的时刻（同 `candle_time` 语义）。

---

## 1. 因子输出外壳（必须一致）

### 1.1 `FactorSlice`

每个因子在时刻 `at_time` 的对外快照结构：

```ts
type FactorSliceV1 = {
  schema_version: 1
  history: unknown
  head: unknown
  meta: {
    series_id: string
    epoch: number
    at_time: number
    candle_id: string
    factor_name: string

    // 可选：仅用于窗口内展示/加速；不得作为持久化主键
    at_idx?: number

    // 可选：用于可复现/缓存（实现可延后）
    params_hash?: string
    logic_hash?: string
  }
}
```

约束：
- `meta.at_time` 必须等于本次 slice 对齐后的 `candle_time`。
- `candle_id` 必须可由 `series_id + at_time` 决定（见 `market-kline-sync`）。

### 1.2 `deps_snapshot`

下游因子读取上游因子输出时，只允许读取 registry 传入的 `deps_snapshot`（只读）：

```ts
type DepsSnapshotV1 = Record<string, FactorSliceV1>
```

> 禁止：在切片阶段回调依赖因子的 `slice_at()`（会导致递归切片/重复计算/未来函数风险）。

---

## 2. 因子“类”应声明的静态信息（结构，而非实现）

```ts
type FactorSpecV1 = {
  factor_name: string               // 稳定 key（跨版本尽量不改名）
  depends_on: string[]              // 因子拓扑依赖（按 factor_name）
  params_schema: Record<string, any>// JSON 友好的 params（可用 jsonschema/zod/pydantic 表达）
  history_schema: Record<string, any>
  head_schema: Record<string, any>

  // 可复现性：逻辑版本（源码 hash / 手工版本号均可，但必须稳定）
  logic_hash: string
}
```

建议：
- `factor_name` 用稳定短名（如 `pivot`/`pen`），不要包含运行期参数。
- 需要“动态多实例因子”（如 `gp_entry__<id>`）时，仍要求能从 `factor_name` 推回到“静态模板名 + 实例 id”。

---

## 3. `history/head` 的语义与不变量

### 3.1 `history`（冷数据，append-only）

定义：
- `history` 表示“在 t 时刻可确认为真的结构化事实/事件流”。
- `history` 的更新必须是 **append-only**（允许在极端尾部修订时出现“同 key 多版本”，但语义上仍是“追加新版本”，不能原地改写旧记录）。

硬约束：
- `slice_history(at_time)` 必须是 **纯切片**（仅过滤/二分/截断），禁止重算。
- 任何事件/结构如果需要可见性，必须带 `visible_time`（或等价字段），并满足 `visible_time <= at_time` 才能在 slice 输出中出现。

### 3.2 `head`（热数据，短窗动态）

定义：
- `head` 表示“在 t 时刻可用于决策/展示，但可能随后续 K 线重绘”的动态状态（如最后一笔、延伸段、当前候选信号等）。

硬约束：
- `slice_head(at_time)` 允许短窗重算，但必须严格无未来函数：只能使用 `<= at_time` 的输入。
- `head` 必须是 JSON 友好（基础类型 + list/dict），避免携带 dataframe/ndarray 等不可序列化对象。

---

## 4. 推荐的事件/结构字段模式（便于解释与对齐）

对“横跨多个 candle 的结构”（如笔/中枢/背驰），推荐字段：

- `start_time` / `end_time`：结构覆盖的时间范围（Unix seconds）
- `start_idx` / `end_idx`：可选，仅窗口内派生编号（不得持久化依赖）
- `visible_time`：结构/事件在何时刻对外可见（用于避免未来函数）
- `kind/status`：生命周期状态（如 `forming/confirmed/cancelled/dead` 等）

---

## 5. 示例：Pivot 因子（v1 口径示意）

> 示例只用于说明数据结构风格，不绑定具体算法。

```ts
type PivotPointV1 = {
  pivot_time: number
  pivot_price: number
  direction: "resistance" | "support"
  visible_time: number
}

type PivotHistoryV1 = {
  major: PivotPointV1[]  // append-only
}

type PivotHeadV1 = {
  minor: PivotPointV1[]  // 允许短窗重算/重绘
}

type PivotSliceV1 = FactorSliceV1 & {
  history: PivotHistoryV1
  head: PivotHeadV1
}
```

---

## 6. 失败模式（用于设计门禁）

- `meta.at_time` 与输入 candle 不一致（下游对齐必炸）。
- `history` 通过“末态倒推”重算导致未来函数（`seed(2000)+slice(1000)` 与 `seed(1000)+slice(1000)` 不一致）。
- `deps_snapshot` 被下游原地改写导致上游数据污染（必须 copy-on-write）。

