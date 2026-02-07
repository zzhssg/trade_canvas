---
title: Replay Package Contract v1（复盘包：SQLite 存储协议）
status: draft
created: 2026-02-06
updated: 2026-02-06
---

# Replay Package Contract v1（复盘包：SQLite 存储协议）

目标：定义 replay 包的**落盘协议**与**存取语义**，满足：
- **history/head 分离**：history 为 append-only；head 为每根 K 线独立快照。
- **全量 + 差值**：任意时刻可重建全量（history slice + head snapshot + draw state），并提供差值更新数据。
- **可复现**：cache_key 稳定，同输入同输出。
- **可窗口化**：window 切片读取，避免首包过大。

关联契约：
- 因子外壳：`docs/core/contracts/factor_v1.md`
- 因子账本：`docs/core/contracts/factor_ledger_v1.md`
- 绘图增量：`docs/core/contracts/draw_delta_v1.md`
- 回放帧：`docs/core/contracts/replay_frame_v1.md`

## 1) 存储介质与路径

- 介质：SQLite 文件（每个 replay 包一个数据库）。
- 推荐路径：`backend/data/artifacts/replay_package_v1/<cache_key>/replay.sqlite`
- 约束：**只读访问**不触发重算；构建是显式行为。

## 2) 时间主键与窗口

- `idx`：窗口内稳定序号，从 0 递增（与 K 线顺序一致）。
- `candle_time`：闭合 K 线时间（Unix seconds）。
- `window_index = idx // window_size`；窗口数据必须可独立加载与重建。

## 3) 关键语义（history/head 分离）

### 3.1 history（append-only）

- history 以事件流落盘（append-only），读取时只做切片：
  - `history_at(t) = events WHERE candle_time <= t`
- **禁止重算**：切片是纯过滤（允许用索引加速）。

### 3.2 head（每根 K 线独立快照）

- 每个 `candle_time` 必须有一份 `head` 快照（按 factor 分类）。
- 允许同一 `candle_time` 追加新版本（尾部修订），以 `seq` 区分，读取取 `seq` 最大。
- head 读取不允许未来函数：只允许 `<= t` 的输入。

## 4) SQLite Schema（v1）

### 4.1 元信息（单行）

```sql
CREATE TABLE replay_meta (
  schema_version INTEGER NOT NULL,
  cache_key TEXT NOT NULL,
  series_id TEXT NOT NULL,
  timeframe_s INTEGER NOT NULL,
  total_candles INTEGER NOT NULL,
  from_candle_time INTEGER NOT NULL,
  to_candle_time INTEGER NOT NULL,
  window_size INTEGER NOT NULL,
  snapshot_interval INTEGER NOT NULL,
  preload_offset INTEGER NOT NULL DEFAULT 0,
  idx_to_time TEXT NOT NULL DEFAULT 'replay_kline_bars.candle_time',
  candle_store_head_time INTEGER NOT NULL,
  factor_store_last_event_id INTEGER NOT NULL,
  overlay_store_last_version_id INTEGER NOT NULL,
  created_at_ms INTEGER NOT NULL
);
```

### 4.2 K 线（source of truth）

```sql
CREATE TABLE replay_kline_bars (
  idx INTEGER PRIMARY KEY,
  candle_time INTEGER NOT NULL,
  open REAL NOT NULL,
  high REAL NOT NULL,
  low REAL NOT NULL,
  close REAL NOT NULL,
  volume REAL NOT NULL
);
CREATE INDEX idx_replay_kline_time ON replay_kline_bars(candle_time);
```

### 4.3 窗口元信息

```sql
CREATE TABLE replay_window_meta (
  window_index INTEGER PRIMARY KEY,
  start_idx INTEGER NOT NULL,
  end_idx INTEGER NOT NULL,
  start_time INTEGER NOT NULL,
  end_time INTEGER NOT NULL
);
```

### 4.4 history 事件（append-only）

```sql
CREATE TABLE replay_factor_history_events (
  event_id INTEGER PRIMARY KEY,
  series_id TEXT NOT NULL,
  factor_name TEXT NOT NULL,
  candle_time INTEGER NOT NULL,
  kind TEXT NOT NULL,
  event_key TEXT NOT NULL,
  payload_json TEXT NOT NULL
);
CREATE INDEX idx_replay_history_time ON replay_factor_history_events(candle_time);
CREATE INDEX idx_replay_history_factor_time ON replay_factor_history_events(factor_name, candle_time);
```

> 语义：`history_at(t)` 仅做 `candle_time <= t` 的过滤切片。

### 4.5 head 快照（每根 K 线独立）

```sql
CREATE TABLE replay_factor_head_snapshots (
  series_id TEXT NOT NULL,
  factor_name TEXT NOT NULL,
  candle_time INTEGER NOT NULL,
  seq INTEGER NOT NULL,
  head_json TEXT NOT NULL,
  PRIMARY KEY (series_id, factor_name, candle_time, seq)
);
CREATE INDEX idx_replay_head_factor_time ON replay_factor_head_snapshots(factor_name, candle_time, seq);
```

> 语义：`head_at(t)` 取 `candle_time == t` 且 `seq` 最大的快照（若允许尾部修订）。

### 4.6 history 差值（事件 id 范围）

```sql
CREATE TABLE replay_factor_history_deltas (
  idx INTEGER PRIMARY KEY,
  from_event_id INTEGER NOT NULL,
  to_event_id INTEGER NOT NULL
);
```

> 语义：`delta_history(idx)` = `(from_event_id, to_event_id]` 区间内的新增事件。

### 4.7 draw catalog（版本化定义）

```sql
CREATE TABLE replay_draw_catalog_versions (
  version_id INTEGER PRIMARY KEY,
  instruction_id TEXT NOT NULL,
  kind TEXT NOT NULL,
  visible_time INTEGER NOT NULL,
  definition_json TEXT NOT NULL
);
CREATE INDEX idx_replay_draw_catalog_visible ON replay_draw_catalog_versions(visible_time);
```

### 4.8 draw catalog 窗口切片

```sql
CREATE TABLE replay_draw_catalog_window (
  window_index INTEGER NOT NULL,
  scope TEXT NOT NULL, -- 'base' | 'patch'
  version_id INTEGER NOT NULL,
  PRIMARY KEY (window_index, scope, version_id)
);
```

### 4.9 draw active_ids（checkpoint + diff）

```sql
CREATE TABLE replay_draw_active_checkpoints (
  window_index INTEGER NOT NULL,
  at_idx INTEGER NOT NULL,
  active_ids_json TEXT NOT NULL,
  PRIMARY KEY (window_index, at_idx)
);

CREATE TABLE replay_draw_active_diffs (
  window_index INTEGER NOT NULL,
  at_idx INTEGER NOT NULL,
  add_ids_json TEXT NOT NULL,
  remove_ids_json TEXT NOT NULL,
  PRIMARY KEY (window_index, at_idx)
);
```

> 语义：通过 `checkpoint + diffs` 可重建任意 idx 的 active_ids。

## 5) 全量与差值的重建规则

### 5.1 全量（t 帧）

给定 `idx -> candle_time`：
1) `history`：切片 `replay_factor_history_events`（`candle_time <= t`）
2) `head`：读取 `replay_factor_head_snapshots`（`candle_time == t`）
3) `draw`：窗口内 `catalog_base + catalog_patch` + `active_ids` 重建

### 5.2 差值（idx-1 -> idx）

- `history_delta`：`replay_factor_history_deltas` 指示新增事件范围
- `head_delta`：视为 **replace**（直接切到 `candle_time == t` 的 head 快照）
- `draw_delta`：由 `catalog_patch`（version_id 增量）与 `active_ids` diff 提供

## 6) 一致性与门禁（必须可测）

1) 对齐：`candle_id` 与 `history/head/draw` 均对齐到同一 `candle_time`
2) 可复现：固定 fixtures 构建包，重复重建同一 `t`，结果一致
3) 幂等：重复构建不改变 `cache_key`，重建结果一致

