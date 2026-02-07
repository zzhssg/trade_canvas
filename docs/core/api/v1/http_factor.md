---
title: API v1 · Factor（HTTP）
status: draft
created: 2026-02-03
updated: 2026-02-08
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
- fail-safe（logic hash）：
  - 当 `factor_series_state.logic_hash` 缺失：返回 `409 stale_factor_logic_hash:missing`
  - 当运行时逻辑 hash 与落库 hash 不一致：返回 `409 stale_factor_logic_hash:mismatch:*`

## POST /api/factor/rebuild

用途：当 factor 逻辑 hash 失配导致读口 `409` 时，按当前代码重新构建指定 `series_id` 的 factor（可选 overlay）。
该能力默认关闭（高风险写路径），需设置 `TRADE_CANVAS_ENABLE_FACTOR_REBUILD=1` 才可访问。

### 请求体（json）

```json
{
  "series_id": "binance:futures:BTC/USDT:1m",
  "include_overlay": true
}
```

### 示例（curl）

```bash
curl --noproxy '*' -sS -X POST "http://127.0.0.1:8000/api/factor/rebuild" \
  -H "Content-Type: application/json" \
  -d '{"series_id":"binance:futures:BTC/USDT:1m","include_overlay":true}'
```

### 响应体（json）

```json
{
  "ok": true,
  "series_id": "binance:futures:BTC/USDT:1m",
  "rebuilt_to_time": 1700000000,
  "factor_logic_hash": "c8f0...e9",
  "include_overlay": true
}
```

### 语义

- `series_id` 必填；会以该序列当前 `candle_store` 对齐头部作为重建目标时刻。
- `include_overlay=true` 时，会在 factor 重建后同步重建 overlay，避免 world/frame 读到旧绘图状态。
- 重建成功后，`factor_series_state.logic_hash` 会更新为当前运行逻辑 hash，之前的 `stale_factor_logic_hash:*` 应恢复为可读。
- 当 `TRADE_CANVAS_ENABLE_FACTOR_REBUILD` 未开启时，接口返回 `404 not_found`。
