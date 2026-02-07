---
title: API v1 · Replay（HTTP）
status: in_progress
created: 2026-02-06
updated: 2026-02-06
---

# API v1 · Replay（HTTP）

复盘包的读/建流程：`read_only -> ensure_coverage (可选) -> build -> status -> window`。

约束（硬门禁）：
- 复盘只对齐 closed candles（`aligned_time`）。
- `history/head` 分离：history append-only 切片；head 每根 K 单独快照。
- 读路径只读：read-only 不触发隐式构建或重算。

---

## GET /api/replay/read_only

只读探测：检查是否已有可用复盘包（不触发构建）。

### 示例（curl）

```bash
curl --noproxy '*' -sS \
  "http://127.0.0.1:8000/api/replay/read_only?series_id=binance:futures:BTC/USDT:1m&window_candles=2000&window_size=500&snapshot_interval=25"
```

### 示例响应（json）

```json
{
  "status": "build_required",
  "job_id": "2d2f9e0fbd1c4a98b0e8c9ab",
  "cache_key": "2d2f9e0fbd1c4a98b0e8c9ab",
  "coverage": {
    "required_candles": 2000,
    "candles_ready": 1378,
    "from_time": 1699991720,
    "to_time": 1700000000
  },
  "compute_hint": "build_required: replay package not cached"
}
```

### 语义

- `status`：`done | build_required | coverage_missing | out_of_sync`
- `coverage`：用于判断是否需要先补齐数据（candles < 2000 则 coverage_missing）
- `read_only` 不触发构建或补齐，只给出提示与 cache_key

---

## POST /api/replay/ensure_coverage

显式补齐历史数据，确保最近 `target_candles` 根 closed K 可用。

### 示例（curl）

```bash
curl --noproxy '*' -sS \
  -X POST "http://127.0.0.1:8000/api/replay/ensure_coverage" \
  -H "content-type: application/json" \
  -d '{
    "series_id": "binance:futures:BTC/USDT:1m",
    "target_candles": 2000,
    "to_time": 1700000000
  }'
```

### 示例请求（json）

```json
{
  "series_id": "binance:futures:BTC/USDT:1m",
  "target_candles": 2000,
  "to_time": 1700000000
}
```

### 示例响应（json）

```json
{
  "status": "building",
  "job_id": "coverage_2d2f9e0fbd1c4a98b0e8c9ab"
}
```

### 语义

- 触发补齐任务（可能使用 freqtrade datadir 或 CCXT backfill）
- 任务完成后必须保证因子与绘图写链路推进到相同 `to_time`

---

## GET /api/replay/coverage_status

查询补齐进度。

### 示例（curl）

```bash
curl --noproxy '*' -sS \
  "http://127.0.0.1:8000/api/replay/coverage_status?job_id=coverage_2d2f9e0fbd1c4a98b0e8c9ab"
```

### 示例响应（json）

```json
{
  "status": "done",
  "job_id": "coverage_2d2f9e0fbd1c4a98b0e8c9ab",
  "candles_ready": 2000,
  "required_candles": 2000,
  "head_time": 1700000000
}
```

### 语义

- `status`：`building | done | error`
- `candles_ready` 达标后才允许进入 build

---

## POST /api/replay/build

显式构建复盘包（SQLite）。

### 示例（curl）

```bash
curl --noproxy '*' -sS \
  -X POST "http://127.0.0.1:8000/api/replay/build" \
  -H "content-type: application/json" \
  -d '{
    "series_id": "binance:futures:BTC/USDT:1m",
    "to_time": 1700000000,
    "window_candles": 2000,
    "window_size": 500,
    "snapshot_interval": 25
  }'
```

### 示例请求（json）

```json
{
  "series_id": "binance:futures:BTC/USDT:1m",
  "to_time": 1700000000,
  "window_candles": 2000,
  "window_size": 500,
  "snapshot_interval": 25
}
```

### 示例响应（json）

```json
{
  "status": "building",
  "job_id": "2d2f9e0fbd1c4a98b0e8c9ab",
  "cache_key": "2d2f9e0fbd1c4a98b0e8c9ab"
}
```

### 语义

- build 必须显式触发；read-only 不隐式构建
- 构建完成后生成 SQLite 包（见 `docs/core/contracts/replay_package_v1.md`）

---

## GET /api/replay/status

构建状态查询；可选首包数据。

### 示例（curl）

```bash
curl --noproxy '*' -sS \
  "http://127.0.0.1:8000/api/replay/status?job_id=2d2f9e0fbd1c4a98b0e8c9ab&include_preload=1&include_history=1"
```

### 示例响应（json）

```json
{
  "status": "done",
  "job_id": "2d2f9e0fbd1c4a98b0e8c9ab",
  "cache_key": "2d2f9e0fbd1c4a98b0e8c9ab",
  "metadata": {
    "schema_version": 1,
    "series_id": "binance:futures:BTC/USDT:1m",
    "timeframe_s": 60,
    "total_candles": 2000,
    "from_candle_time": 1699880000,
    "to_candle_time": 1700000000,
    "window_size": 500,
    "snapshot_interval": 25
  },
  "preload_window": {
    "window_index": 3,
    "start_idx": 1500,
    "end_idx": 2000,
    "kline": [
      {"time": 1699999940, "open": 43000, "high": 43120, "low": 42950, "close": 43050, "volume": 12.5}
    ],
    "draw_catalog_base": [],
    "draw_catalog_patch": [],
    "draw_active_checkpoints": [],
    "draw_active_diffs": []
  },
  "history_events": [
    {
      "event_id": 1201,
      "factor_name": "pivot",
      "candle_time": 1699999800,
      "kind": "pivot.major",
      "event_key": "major:1699999800:support:50",
      "payload": {"pivot_time": 1699999800, "pivot_price": 43000, "direction": "support", "visible_time": 1699999860}
    }
  ]
}
```

### 语义

- `include_preload=1`：返回首包窗口（减少首次 /window 请求）
- `include_history=1`：返回全量 history 事件（append-only）
- `history_events` 用于前端按 `event_id` 做切片；head 则由 /window 返回每根快照

---

## GET /api/replay/window

按 `idx` 读取窗口数据（含 head 快照 + draw window）。

### 示例（curl）

```bash
curl --noproxy '*' -sS \
  "http://127.0.0.1:8000/api/replay/window?job_id=2d2f9e0fbd1c4a98b0e8c9ab&target_idx=1530"
```

### 示例响应（json）

```json
{
  "job_id": "2d2f9e0fbd1c4a98b0e8c9ab",
  "window": {
    "window_index": 3,
    "start_idx": 1500,
    "end_idx": 2000,
    "kline": [
      {"time": 1699999940, "open": 43000, "high": 43120, "low": 42950, "close": 43050, "volume": 12.5}
    ],
    "draw_catalog_base": [],
    "draw_catalog_patch": [],
    "draw_active_checkpoints": [
      {"at_idx": 1500, "active_ids": ["pivot.major:1699999800:support:50"]}
    ],
    "draw_active_diffs": [
      {"at_idx": 1501, "add_ids": [], "remove_ids": []}
    ]
  },
  "factor_head_snapshots": [
    {
      "factor_name": "pen",
      "candle_time": 1699999940,
      "seq": 0,
      "head": {"candidate": {"start_time": 1699999200, "end_time": 1699999940, "direction": 1}}
    }
  ],
  "history_deltas": [
    {"idx": 1501, "from_event_id": 1201, "to_event_id": 1203}
  ]
}
```

### 语义

- `window.kline`：该窗口的闭合 K（`time` 为 Unix seconds）
- `factor_head_snapshots`：每根 K 的 head 快照（按 factor 分类）
- `history_deltas`：用于 idx 增量播放时的 history 事件范围
- draw window 使用 `catalog_base + catalog_patch + active_ids` 重建图元

---

## 开关与失败语义

- 后端 kill-switch：`TRADE_CANVAS_ENABLE_REPLAY_V1=1`
- coverage 失败：返回 `coverage_missing`
- 对齐失败：返回 `out_of_sync`（例如 overlay/factor 未推进到位）
