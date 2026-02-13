---
title: API v1 · Replay（HTTP）
status: done
created: 2026-02-06
updated: 2026-02-13
---

# API v1 · Replay（HTTP）

复盘包流程（最终口径）：`prepare -> ensure_coverage(可选) -> build -> status -> window`。

约束（硬门禁）：
- 复盘只对齐 closed candles（`aligned_time`）。
- 读路径只读：不提供 read-only 探测兼容接口，不做隐式构建或隐式重算。
- replay package 与 overlay package 都是显式 build，status/window 只消费已存在 job/cache。

---

## POST /api/replay/prepare

回放准备：确保 factor/overlay 已计算到请求时间的对齐闭合 K。

### 示例请求（curl）

```bash
curl --noproxy '*' -sS -X POST \
  "http://127.0.0.1:8000/api/replay/prepare" \
  -H "Content-Type: application/json" \
  -d '{"series_id":"binance:futures:BTC/USDT:1m","to_time":1700000005,"window_candles":2000}'
```

### 示例请求体（json）

```json
{
  "series_id": "binance:futures:BTC/USDT:1m",
  "to_time": 1700000005,
  "window_candles": 2000
}
```

### 示例响应（json）

```json
{
  "ok": true,
  "series_id": "binance:futures:BTC/USDT:1m",
  "requested_time": 1700000005,
  "aligned_time": 1700000000,
  "window_candles": 2000,
  "factor_head_time": 1700000000,
  "overlay_head_time": 1700000000,
  "computed": true
}
```

### 语义

- 若 factor/overlay 未追到 `aligned_time`，返回 `409 ledger_out_of_sync:*`。

---

## POST /api/replay/build

显式触发 replay package 构建。

### 示例请求（curl）

```bash
curl --noproxy '*' -sS \
  -X POST "http://127.0.0.1:8000/api/replay/build" \
  -H "content-type: application/json" \
  -d '{"series_id":"binance:futures:BTC/USDT:1m","window_candles":2000,"window_size":500,"snapshot_interval":25}'
```

### 示例请求体（json）

```json
{
  "series_id": "binance:futures:BTC/USDT:1m",
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

- 若 candles 覆盖不足，返回 `409 coverage_missing`（先走 `ensure_coverage`）。
- 若 factor/overlay 未对齐到目标时间，返回 `409 ledger_out_of_sync:replay`。

---

## GET /api/replay/status

查询构建状态（`building | done | error`）。

### 示例请求（curl）

```bash
curl --noproxy '*' -sS \
  "http://127.0.0.1:8000/api/replay/status?job_id=2d2f9e0fbd1c4a98b0e8c9ab&include_preload=1&include_history=1"
```

### 示例响应（json，done）

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
    "from_candle_time": 1699880060,
    "to_candle_time": 1700000000,
    "window_size": 500,
    "snapshot_interval": 25,
    "preload_offset": 0,
    "idx_to_time": "replay_kline_bars.candle_time"
  }
}
```

### 语义

- `job_id` 不存在且缓存不存在时返回 `404 not_found`。

---

## GET /api/replay/window

读取目标 idx 对应窗口。

### 示例请求（curl）

```bash
curl --noproxy '*' -sS \
  "http://127.0.0.1:8000/api/replay/window?job_id=2d2f9e0fbd1c4a98b0e8c9ab&target_idx=0"
```

### 示例响应（json）

```json
{
  "window": {
    "target_idx": 0,
    "from_idx": 0,
    "to_idx": 499,
    "candles": []
  },
  "factor_head_snapshots": [],
  "history_deltas": []
}
```

### 语义

- 返回 `window + factor_head_snapshots + history_deltas`。
- `job_id` 不存在或缓存缺失返回 `404 not_found`。

---

## POST /api/replay/ensure_coverage

显式补齐历史数据，确保最近 `target_candles` 根 closed K 可用。

### 示例请求（curl）

```bash
curl --noproxy '*' -sS \
  -X POST "http://127.0.0.1:8000/api/replay/ensure_coverage" \
  -H "content-type: application/json" \
  -d '{"series_id":"binance:futures:BTC/USDT:1m","target_candles":2000,"to_time":1700000000}'
```

### 示例请求体（json）

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
  "job_id": "coverage_binance:futures:BTC/USDT:1m:1700000000:2000"
}
```

### 语义

- 若 `to_time` 落在 forming 区间，会先对齐到最近 closed K 再进行覆盖检查。
- 当历史覆盖已满足目标时，可能直接返回 `done` 状态（实现可配置）。

---

## GET /api/replay/coverage_status

### 示例请求（curl）

```bash
curl --noproxy '*' -sS \
  "http://127.0.0.1:8000/api/replay/coverage_status?job_id=coverage_binance:futures:BTC/USDT:1m:1700000000:2000"
```

### 示例响应（json，done）

```json
{
  "status": "done",
  "job_id": "coverage_binance:futures:BTC/USDT:1m:1700000000:2000",
  "candles_ready": 2000,
  "required_candles": 2000,
  "head_time": 1700000000
}
```

### 语义

- `status` 可能为 `building | done | error`，用于串联 `ensure_coverage -> build` 流程。

---

## POST /api/replay/overlay_package/build

显式构建 overlay-only replay package。

### 示例请求（curl）

```bash
curl --noproxy '*' -sS \
  -X POST "http://127.0.0.1:8000/api/replay/overlay_package/build" \
  -H "content-type: application/json" \
  -d '{"series_id":"binance:futures:BTC/USDT:1m","window_candles":2000,"window_size":500,"snapshot_interval":25}'
```

### 示例请求体（json）

```json
{
  "series_id": "binance:futures:BTC/USDT:1m",
  "window_candles": 2000,
  "window_size": 500,
  "snapshot_interval": 25
}
```

### 示例响应（json）

```json
{
  "status": "building",
  "job_id": "f0b2c3d4e5a6b7c8d9e0a1b2",
  "cache_key": "f0b2c3d4e5a6b7c8d9e0a1b2"
}
```

### 语义

- 只构建 overlay 视图数据（不回传 factor history），用于轻量回放或图表联调。

---

## GET /api/replay/overlay_package/status

查询 overlay package 构建状态（`building | done | error`）。

### 示例请求（curl）

```bash
curl --noproxy '*' -sS \
  "http://127.0.0.1:8000/api/replay/overlay_package/status?job_id=f0b2c3d4e5a6b7c8d9e0a1b2"
```

### 示例响应（json）

```json
{
  "status": "done",
  "job_id": "f0b2c3d4e5a6b7c8d9e0a1b2",
  "cache_key": "f0b2c3d4e5a6b7c8d9e0a1b2"
}
```

### 语义

- `job_id` 不存在且缓存不存在时返回 `404 not_found`。

---

## GET /api/replay/overlay_package/window

### 示例请求（curl）

```bash
curl --noproxy '*' -sS \
  "http://127.0.0.1:8000/api/replay/overlay_package/window?job_id=f0b2c3d4e5a6b7c8d9e0a1b2&target_idx=0"
```

### 示例响应（json）

```json
{
  "window": {
    "target_idx": 0,
    "from_idx": 0,
    "to_idx": 499
  },
  "kline": [],
  "catalog_base": [],
  "catalog_patch": [],
  "checkpoints": [],
  "diffs": []
}
```

### 语义

- 返回 overlay replay window（kline/catalog_base/catalog_patch/checkpoints/diffs）。
