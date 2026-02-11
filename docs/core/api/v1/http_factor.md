---
title: API v1 · Factor（HTTP）
status: done
created: 2026-02-03
updated: 2026-02-11
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
