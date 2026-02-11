---
title: Factor Ledger Contract v1（冷热真源账本）
status: done
created: 2026-02-02
updated: 2026-02-11
---

# Factor Ledger Contract v1（冷热真源账本）

目标：定义 trade_canvas 的“因子真源账本”最小落地契约，满足：

- **冷数据（history）**：事件驱动、append-only、支持任意 `t` 定点切片（纯过滤）。
- **热数据（head）**：局部热数据快照、append-only、支持任意 `t` 定点查询（点查 / floor）。
- **可复现性**：`seed ≡ incremental`，同输入同输出。
- **fail-safe**：若 `candle_id` 不一致或账本未推进到位，下游（策略/绘图）必须拒绝输出。

关联契约：
- 因子外壳与冷热语义：`docs/core/contracts/factor_v1.md`
- K 线主键：`docs/core/market-kline-sync.md`

> 说明：本契约继承 trade_system 的不变量（time 主键、冷热语义、读写分离），但不要求复刻其文件 ledger 实现；SQLite/file 都可，只要满足语义。

## 1. 统一主键与对齐

- 账本的时间主键：`candle_time`（Unix seconds，等价于 `visible_time` / `at_time` 的对齐刻度）。
- `candle_id`：必须可由 `series_id + candle_time` 决定（见 `market-kline-sync`）。

## 2. 冷账本（Cold / History Ledger）

### 2.1 记录模型（抽象）

```ts
type FactorHistoryEventV1 = {
  id: number                 // 单调递增（cursor）
  series_id: string
  factor_name: string
  candle_time: number        // 本事件“可见时刻”（visible_time）
  kind: string               // 例如 "pivot.major" / "pen.confirmed" / "zhongshu.dead"
  event_key: string          // 幂等 key（同一事件重复写入必须去重）
  payload: Record<string, any>
}
```

硬约束：
- append-only：只能追加新事件；允许“尾部修订”以追加新版本表达，但不得原地改写旧事件语义。
- `slice_history(at_time)` 必须是纯切片：只按 `candle_time <= at_time` 过滤（可二分/索引加速），禁止重算。

### 2.2 幂等（必须可落地）

同一批 `CandleClosed` 被重复 ingest 时，写入必须幂等：
- 推荐以 `UNIQUE(series_id,factor_name,event_key)` 或等价去重约束实现。

## 3. 热账本（Hot / Head Snapshot Ledger）

### 3.1 记录模型（抽象）

```ts
type FactorHeadSnapshotV1 = {
  id: number                 // 单调递增（cursor）
  series_id: string
  factor_name: string
  candle_time: number        // 快照对齐的时刻（= at_time）
  head: Record<string, any>  // JSON 友好
  seq: number                // 同一 candle_time 的版本序号（tail upsert 用；读取取最大 seq）
}
```

硬约束：
- append-only：同一 `candle_time` 的 head 若发生变化（尾部修订/重算），必须以 `seq+1` 的新记录追加表达。
- 定点查询：`get_head_at_or_before(t)` 必须返回 `candle_time<=t` 的最近一条记录（若存在同 `candle_time` 多版本，取 `seq` 最大）。
- 禁止未来函数：任何 `head` 字段只允许来自 `<=t` 的输入。

## 4. 进度指针（非真源，可 upsert）

账本需要一个“推进度”指针（例如 `series_head_time`）用于快速判断是否已 ingest 到位：
- 该指针不是事实真源，可以 upsert（它只是“我已处理到哪”）。
- fail-safe：若 `series_head_time < requested_time`，读路径必须返回 `ledger_out_of_sync`（409），禁止隐式写入或隐式全量重算。

## 5. 最小校验矩阵（必须可自动化）

1) `seed ≡ incremental`：全量 seed 结果 == 逐根 apply_closed 结果（至少对 `pivot→pen→zhongshu` 的关键产物对拍）。
2) 幂等：重复 ingest 同一段 candles，不产生重复 history/head 记录（或只产生“更大 seq”的尾部版本，且读取语义一致）。
3) 切片纯度：`seed(2000)+slice(1000)` == `seed(1000)+slice(1000)`（避免末态倒推/未来函数）。
