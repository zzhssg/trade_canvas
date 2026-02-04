---
title: API v1 · Factor（HTTP）
status: draft
created: 2026-02-03
updated: 2026-02-03
---

# API v1 · Factor（HTTP）

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

