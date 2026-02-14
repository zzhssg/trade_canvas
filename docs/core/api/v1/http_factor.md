---
title: API v1 · Factor（HTTP）
status: done
created: 2026-02-03
updated: 2026-02-14
---

# API v1 · Factor（HTTP）

## GET /api/factor/catalog

返回前端因子面板的动态目录（因子顺序与后端 factor manifest 拓扑一致），用于替代前端硬编码目录。

### 示例（curl）

```bash
curl --noproxy '*' -sS \
  "http://127.0.0.1:8000/api/factor/catalog"
```

### 示例响应（json）

```json
{
  "schema_version": 1,
  "factors": [
    {
      "key": "pivot",
      "label": "Pivot",
      "default_visible": true,
      "sub_features": [
        {"key": "pivot.major", "label": "Major", "default_visible": true},
        {"key": "pivot.minor", "label": "Minor", "default_visible": false}
      ]
    },
    {
      "key": "sma",
      "label": "SMA",
      "default_visible": false,
      "sub_features": [
        {"key": "sma_5", "label": "SMA 5", "default_visible": false},
        {"key": "sma_20", "label": "SMA 20", "default_visible": false}
      ]
    }
  ]
}
```

### 语义

- `factors` 中标准因子来自后端 manifest（拓扑顺序）与插件 `spec.catalog`（展示元信息）。
- `sma` / `signal` 作为前端展示用虚拟分组，由后端目录接口统一追加。
- 当前端无法访问该接口时，可降级到本地 fallback 目录，保证可用性。

## GET /api/factor/health

返回当前 `series_id` 的因子/绘图追平状态，基准是 `candle_store.head_time`（也就是图表最新 closed K 线）。

### 示例（curl）

```bash
curl --noproxy '*' -sS \
  "http://127.0.0.1:8000/api/factor/health?series_id=binance:futures:BTC/USDT:5m"
```

### 示例响应（json）

```json
{
  "series_id": "binance:futures:BTC/USDT:5m",
  "timeframe_seconds": 300,
  "store_head_time": 1735689900,
  "factor_head_time": 1735689600,
  "overlay_head_time": 1735689600,
  "factor_delay_seconds": 300,
  "factor_delay_candles": 1,
  "overlay_delay_seconds": 300,
  "overlay_delay_candles": 1,
  "max_delay_seconds": 300,
  "max_delay_candles": 1,
  "status": "yellow",
  "status_reason": "lagging_one_candle"
}
```

### 语义

- `status=green`：因子和绘图都追平了最新 closed K 线。
- `status=yellow`：存在 1 根 K 线以内延迟（轻微滞后）。
- `status=red`：缺失因子/绘图头部，或延迟超过 1 根 K 线。
- `status=gray`：K 线主存储还没有可用 head（`store_head_time` 为空）。
- `*_delay_seconds` / `*_delay_candles` 以 `store_head_time` 为目标计算，若对应头缺失则为 `null`。

## GET /api/factor/slices

### 示例（curl）

```bash
curl --noproxy '*' -sS \
  "http://127.0.0.1:8000/api/factor/slices?series_id=binance:futures:BTC/USDT:1m&at_time=1700000000&window_candles=2000"
```

### 示例响应（json）

```json
{
  "schema_version": 1,
  "series_id": "binance:futures:BTC/USDT:1m",
  "at_time": 1700000000,
  "candle_id": "binance:futures:BTC/USDT:1m:1700000000",
  "factors": ["pivot"],
  "snapshots": {
    "pivot": {
      "schema_version": 1,
      "history": {"major": [], "minor": []},
      "head": {},
      "meta": {
        "series_id": "binance:futures:BTC/USDT:1m",
        "epoch": 0,
        "at_time": 1700000000,
        "candle_id": "binance:futures:BTC/USDT:1m:1700000000",
        "factor_name": "pivot"
      }
    }
  }
}
```

### 语义

- 该接口用于调试/观测：查询某个 `at_time` 对齐后的因子切片（history + head）。
- `at_time` 会先 floor 到 closed candle 对齐时间，返回的 `candle_id` 必须和该对齐一致。
- `window_candles` 控制返回的 history 窗口大小（用于减少 payload，避免全量）。
