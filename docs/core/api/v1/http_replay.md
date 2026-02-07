---
title: API v1 · Replay（HTTP）
status: in_progress
created: 2026-02-06
updated: 2026-02-07
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

```bash
curl --noproxy '*' -sS   "http://127.0.0.1:8000/api/replay/read_only?series_id=binance:futures:BTC/USDT:1m&window_candles=2000&window_size=500&snapshot_interval=25"
```

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

- `status`：`done | build_required | coverage_missing | out_of_sync`。
- `coverage`：用于判断是否需要先补齐数据（candles < 2000 则 coverage_missing）。
- `read_only` 不触发构建或补齐，只给出提示与 cache_key。

## POST /api/replay/build

```bash
curl --noproxy '*' -sS   -X POST "http://127.0.0.1:8000/api/replay/build"   -H "content-type: application/json"   -d '{"series_id":"binance:futures:BTC/USDT:1m","window_candles":2000,"window_size":500,"snapshot_interval":25}'
```

```json
{
  "series_id": "binance:futures:BTC/USDT:1m",
  "window_candles": 2000,
  "window_size": 500,
  "snapshot_interval": 25
}
```

```json
{
  "status": "building",
  "job_id": "2d2f9e0fbd1c4a98b0e8c9ab"
}
```

### 语义

- 返回 `job_id` 供后续 status/window 查询。
- 若数据不足，会返回 `status=coverage_missing` 并提示补齐。

## GET /api/replay/status

```bash
curl --noproxy '*' -sS   "http://127.0.0.1:8000/api/replay/status?job_id=2d2f9e0fbd1c4a98b0e8c9ab"
```

```json
{
  "status": "done",
  "job_id": "2d2f9e0fbd1c4a98b0e8c9ab",
  "snapshot_count": 80,
  "window_size": 500,
  "latest_window_id": 79
}
```

### 语义

- `status=done` 表示复盘包已缓存，可直接 window。

## GET /api/replay/window

```bash
curl --noproxy '*' -sS   "http://127.0.0.1:8000/api/replay/window?job_id=2d2f9e0fbd1c4a98b0e8c9ab&target_idx=0"
```

```json
{
  "status": "done",
  "job_id": "2d2f9e0fbd1c4a98b0e8c9ab",
  "window_id": 0,
  "window_total": 80,
  "frame": {
    "series_id": "binance:futures:BTC/USDT:1m",
    "time": {
      "at_time": 1700000000,
      "aligned_time": 1700000000,
      "candle_id": "binance:futures:BTC/USDT:1m:1700000000"
    },
    "factor_slices": null,
    "draw_state": null
  }
}
```

### 语义

- `target_idx` 为窗口序号（从 0 开始）。
- 返回 `frame`（世界状态快照）。

## POST /api/replay/ensure_coverage

显式补齐历史数据，确保最近 `target_candles` 根 closed K 可用。

```bash
curl --noproxy '*' -sS   -X POST "http://127.0.0.1:8000/api/replay/ensure_coverage"   -H "content-type: application/json"   -d '{"series_id":"binance:futures:BTC/USDT:1m","target_candles":2000,"to_time":1700000000}'
```

```json
{
  "series_id": "binance:futures:BTC/USDT:1m",
  "target_candles": 2000,
  "to_time": 1700000000
}
```

```json
{
  "status": "building",
  "job_id": "coverage_2d2f9e0fbd1c4a98b0e8c9ab"
}
```

### 语义

- 触发补齐任务（可能使用 freqtrade datadir 或 CCXT backfill）。
- 任务完成后必须保证因子与绘图写链路推进到相同 `to_time`。

## GET /api/replay/coverage_status

```bash
curl --noproxy '*' -sS   "http://127.0.0.1:8000/api/replay/coverage_status?job_id=coverage_2d2f9e0fbd1c4a98b0e8c9ab"
```

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

- `status=done` 表示补齐完成，可继续 build。

---

## GET /api/replay/overlay_package/read_only

```bash
curl --noproxy '*' -sS   "http://127.0.0.1:8000/api/replay/overlay_package/read_only?series_id=binance:futures:BTC/USDT:1m"
```

```json
{
  "status": "build_required",
  "job_id": "f0b2c3d4e5a6b7c8d9e0a1b2",
  "cache_key": "f0b2c3d4e5a6b7c8d9e0a1b2",
  "window": {"from_time": 1699991720, "to_time": 1700000000}
}
```

### 语义

- overlay 包仅覆盖绘图指令（draw/overlay），不包含 factor_slices。

## POST /api/replay/overlay_package/build

```bash
curl --noproxy '*' -sS   -X POST "http://127.0.0.1:8000/api/replay/overlay_package/build"   -H "content-type: application/json"   -d '{"series_id":"binance:futures:BTC/USDT:1m","window_candles":2000,"window_size":500,"snapshot_interval":25}'
```

```json
{
  "series_id": "binance:futures:BTC/USDT:1m",
  "window_candles": 2000,
  "window_size": 500,
  "snapshot_interval": 25
}
```

```json
{
  "status": "building",
  "job_id": "f0b2c3d4e5a6b7c8d9e0a1b2"
}
```

### 语义

- overlay 包构建只读 overlay_store，不改写 factor_store。

## GET /api/replay/overlay_package/status

```bash
curl --noproxy '*' -sS   "http://127.0.0.1:8000/api/replay/overlay_package/status?job_id=f0b2c3d4e5a6b7c8d9e0a1b2"
```

```json
{
  "status": "done",
  "job_id": "f0b2c3d4e5a6b7c8d9e0a1b2",
  "snapshot_count": 80,
  "window_size": 500,
  "latest_window_id": 79
}
```

### 语义

- status `done` 后才可 window。

## GET /api/replay/overlay_package/window

```bash
curl --noproxy '*' -sS   "http://127.0.0.1:8000/api/replay/overlay_package/window?job_id=f0b2c3d4e5a6b7c8d9e0a1b2&target_idx=0"
```

```json
{
  "status": "done",
  "job_id": "f0b2c3d4e5a6b7c8d9e0a1b2",
  "window_id": 0,
  "window_total": 80,
  "draw_delta": {
    "series_id": "binance:futures:BTC/USDT:1m",
    "to_candle_id": "binance:futures:BTC/USDT:1m:1700000000",
    "to_candle_time": 1700000000,
    "active_ids": [],
    "instruction_catalog_patch": [],
    "series_points": {},
    "next_cursor": {"version_id": 0, "point_time": null}
  }
}
```

### 语义

- 返回 overlay window 的 draw_delta，供前端绘图回放使用。
