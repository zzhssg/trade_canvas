---
title: API v1 · Replay（HTTP）
status: in_progress
created: 2026-02-06
updated: 2026-02-07
---

# API v1 · Replay（HTTP）

复盘主链路：`read_only -> (coverage_missing 时 ensure_coverage) -> build -> status -> window`。

## 开关约束（必须先确认）

- 后端：
  - `TRADE_CANVAS_ENABLE_REPLAY_V1=1` 启用 `/api/replay/*`（关闭时返回 `404 not_found`）
  - `TRADE_CANVAS_ENABLE_REPLAY_ENSURE_COVERAGE=1` 才允许 `ensure_coverage`
- 前端：
  - `VITE_ENABLE_REPLAY_V1=1` 才显示 replay 模式入口
  - `VITE_ENABLE_REPLAY_PACKAGE_V1=1` 才走 replay package 驱动（否则走点查 fallback）

---

## GET /api/replay/read_only

只读探测（不触发构建）。

```bash
curl --noproxy '*' -sS \
  "http://127.0.0.1:8000/api/replay/read_only?series_id=binance:futures:BTC/USDT:1m&window_candles=2000&window_size=500&snapshot_interval=25"
```

示例响应：

```json
{
  "status": "build_required",
  "job_id": "2d2f9e0fbd1c4a98b0e8c9ab",
  "cache_key": "2d2f9e0fbd1c4a98b0e8c9ab",
  "coverage": {
    "required_candles": 2000,
    "candles_ready": 2000,
    "from_time": 1699991720,
    "to_time": 1700000000
  },
  "metadata": null,
  "compute_hint": "build_required: replay package not cached"
}
```

### 语义

- 只读探测，不触发构建。
- `status` 取值：`done | build_required | coverage_missing | out_of_sync`。

## POST /api/replay/build

显式构建 replay package。

```bash
curl --noproxy '*' -sS \
  -X POST "http://127.0.0.1:8000/api/replay/build" \
  -H "content-type: application/json" \
  -d '{"series_id":"binance:futures:BTC/USDT:1m","window_candles":2000,"window_size":500,"snapshot_interval":25}'
```

示例请求：

```json
{
  "series_id": "binance:futures:BTC/USDT:1m",
  "window_candles": 2000,
  "window_size": 500,
  "snapshot_interval": 25
}
```

示例响应：

```json
{
  "status": "building",
  "job_id": "2d2f9e0fbd1c4a98b0e8c9ab",
  "cache_key": "2d2f9e0fbd1c4a98b0e8c9ab"
}
```

### 语义

- 显式构建 replay package；不会隐式触发在 read_only 中。
- 返回 `job_id/cache_key`，后续通过 `status/window` 消费。

## GET /api/replay/status

查询构建状态；可选携带 preload/history。

```bash
curl --noproxy '*' -sS \
  "http://127.0.0.1:8000/api/replay/status?job_id=2d2f9e0fbd1c4a98b0e8c9ab&include_preload=1&include_history=1"
```

示例响应：

```json
{
  "status": "done",
  "job_id": "2d2f9e0fbd1c4a98b0e8c9ab",
  "cache_key": "2d2f9e0fbd1c4a98b0e8c9ab",
  "error": null,
  "metadata": {
    "schema_version": 1,
    "series_id": "binance:futures:BTC/USDT:1m",
    "timeframe_s": 60,
    "total_candles": 2000,
    "from_candle_time": 1699991720,
    "to_candle_time": 1700000000,
    "window_size": 500,
    "snapshot_interval": 25,
    "preload_offset": 0,
    "idx_to_time": "replay_kline_bars.candle_time"
  },
  "preload_window": null,
  "history_events": []
}
```

`status` 取值：`building | done | error | build_required`。

### 语义

- `include_preload=1` 时返回 `preload_window`（用于首屏优化）。
- `include_history=1` 时返回按 `event_id` 升序的 `history_events`。

## GET /api/replay/window

按 `target_idx` 读取窗口切片。

```bash
curl --noproxy '*' -sS \
  "http://127.0.0.1:8000/api/replay/window?job_id=2d2f9e0fbd1c4a98b0e8c9ab&target_idx=0"
```

示例响应（节选）：

```json
{
  "job_id": "2d2f9e0fbd1c4a98b0e8c9ab",
  "window": {
    "window_index": 0,
    "start_idx": 0,
    "end_idx": 500,
    "kline": [],
    "draw_catalog_base": [],
    "draw_catalog_patch": [],
    "draw_active_checkpoints": [],
    "draw_active_diffs": []
  },
  "factor_head_snapshots": [],
  "history_deltas": []
}
```

### 语义

- `target_idx` 必须位于 `[0, total_candles)`，越界返回 `422 target_idx_out_of_range`。
- 返回窗口 K 线 + draw 增量组件 + 因子附加信息（head snapshots / history deltas）。

---

## POST /api/replay/ensure_coverage

显式补齐最近 `target_candles` 根闭合 K。

```bash
curl --noproxy '*' -sS \
  -X POST "http://127.0.0.1:8000/api/replay/ensure_coverage" \
  -H "content-type: application/json" \
  -d '{"series_id":"binance:futures:BTC/USDT:1m","target_candles":2000,"to_time":1700000000}'
```

示例请求：

```json
{
  "series_id": "binance:futures:BTC/USDT:1m",
  "target_candles": 2000,
  "to_time": 1700000000
}
```

示例响应：

```json
{
  "status": "building",
  "job_id": "coverage_binance:futures:BTC/USDT:1m:1700000000:2000",
  "error": null
}
```

### 语义

- 仅在 `TRADE_CANVAS_ENABLE_REPLAY_ENSURE_COVERAGE=1` 时可用。
- 任务会补齐 K 线并尝试推进 factor/overlay 到同一 `to_time`。

## GET /api/replay/coverage_status

```bash
curl --noproxy '*' -sS \
  "http://127.0.0.1:8000/api/replay/coverage_status?job_id=coverage_binance:futures:BTC/USDT:1m:1700000000:2000"
```

示例响应：

```json
{
  "status": "done",
  "job_id": "coverage_binance:futures:BTC/USDT:1m:1700000000:2000",
  "candles_ready": 2000,
  "required_candles": 2000,
  "head_time": 1700000000,
  "error": null
}
```

### 语义

- `status` 取值：`building | done | error`。
- `error=not_found` 场景在 HTTP 层会被转换为 `404`。

---

## Overlay Replay Package（独立开关）

以下接口受 `TRADE_CANVAS_ENABLE_REPLAY_PACKAGE=1` 保护，仅覆盖 draw/overlay，不包含 factor_slices。

## GET /api/replay/overlay_package/read_only

```bash
curl --noproxy '*' -sS \
  "http://127.0.0.1:8000/api/replay/overlay_package/read_only?series_id=binance:futures:BTC/USDT:1m"
```

示例响应：

```json
{
  "status": "build_required",
  "job_id": "f0b2c3d4e5a6b7c8d9e0a1b2",
  "cache_key": "f0b2c3d4e5a6b7c8d9e0a1b2",
  "delta_meta": null,
  "compute_hint": "build_required: overlay replay package not cached"
}
```

### 语义

- 只做缓存探测；不会触发构建。
- `status`：`done | build_required`。

## POST /api/replay/overlay_package/build

```bash
curl --noproxy '*' -sS \
  -X POST "http://127.0.0.1:8000/api/replay/overlay_package/build" \
  -H "content-type: application/json" \
  -d '{"series_id":"binance:futures:BTC/USDT:1m","window_candles":2000,"window_size":500,"snapshot_interval":25}'
```

示例请求：

```json
{
  "series_id": "binance:futures:BTC/USDT:1m",
  "window_candles": 2000,
  "window_size": 500,
  "snapshot_interval": 25
}
```

示例响应：

```json
{
  "status": "building",
  "job_id": "f0b2c3d4e5a6b7c8d9e0a1b2",
  "cache_key": "f0b2c3d4e5a6b7c8d9e0a1b2"
}
```

### 语义

- 显式构建 overlay replay 包，读取源为 overlay_store + candle_store。

## GET /api/replay/overlay_package/status

```bash
curl --noproxy '*' -sS \
  "http://127.0.0.1:8000/api/replay/overlay_package/status?job_id=f0b2c3d4e5a6b7c8d9e0a1b2&include_delta_package=1"
```

示例响应：

```json
{
  "status": "done",
  "job_id": "f0b2c3d4e5a6b7c8d9e0a1b2",
  "cache_key": "f0b2c3d4e5a6b7c8d9e0a1b2",
  "error": null,
  "delta_meta": {
    "schema_version": 1,
    "series_id": "binance:futures:BTC/USDT:1m",
    "to_candle_time": 1700000000,
    "from_candle_time": 1699991720,
    "total_candles": 2000,
    "window_size": 500,
    "snapshot_interval": 25,
    "windows": [],
    "overlay_store_last_version_id": 0
  },
  "kline": [],
  "preload_window": null
}
```

### 语义

- `status`：`building | done | error | build_required`。
- `include_delta_package=1` 时会附加 `kline/preload_window`。

## GET /api/replay/overlay_package/window

```bash
curl --noproxy '*' -sS \
  "http://127.0.0.1:8000/api/replay/overlay_package/window?job_id=f0b2c3d4e5a6b7c8d9e0a1b2&target_idx=0"
```

示例响应：

```json
{
  "job_id": "f0b2c3d4e5a6b7c8d9e0a1b2",
  "window": {
    "window_index": 0,
    "start_idx": 0,
    "end_idx": 500,
    "kline": [],
    "catalog_base": [],
    "catalog_patch": [],
    "checkpoints": [],
    "diffs": [],
    "event_catalog": null
  }
}
```

### 语义

- 按 `target_idx` 命中窗口并返回该窗口 draw 回放数据。
- 越界返回 `422 target_idx_out_of_range`。
