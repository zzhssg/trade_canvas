---
title: API v1 · Market（HTTP + SSE）
status: draft
created: 2026-02-03
updated: 2026-02-10
---

# API v1 · Market（HTTP + SSE）

## GET /api/market/candles

### 示例（curl）

```bash
curl --noproxy '*' -sS \
  "http://127.0.0.1:8000/api/market/candles?series_id=binance:futures:BTC/USDT:1m&since=0&limit=5"
```

### 示例响应（json）

```json
{
  "series_id": "binance:futures:BTC/USDT:1m",
  "server_head_time": 1700000000,
  "candles": [
    {"candle_time": 1700000000, "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 10}
  ]
}
```

### 语义

- 本接口只返回 **closed candles**（append-only 的 history）。
- `since` 为增量游标（当前实现返回 `> since` 的闭合蜡烛，避免重复消费最后一根）。
- `server_head_time` 是服务端已落库的 closed head（用于“前端 catchup 是否追到头”的判断）。

## POST /api/market/ingest/candle_closed

### 示例请求（curl）

```bash
curl --noproxy '*' -sS -X POST "http://127.0.0.1:8000/api/market/ingest/candle_closed" \
  -H 'content-type: application/json' \
  -d '{"series_id":"binance:futures:BTC/USDT:1m","candle":{"candle_time":1700000000,"open":1,"high":2,"low":0.5,"close":1.5,"volume":10}}'
```

### 示例请求体（json）

```json
{
  "series_id": "binance:futures:BTC/USDT:1m",
  "candle": {"candle_time": 1700000000, "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 10}
}
```

### 示例响应（json）

```json
{"ok": true, "series_id": "binance:futures:BTC/USDT:1m", "candle_time": 1700000000}
```

### 语义

- 这是 market history 的写入口：写入后会 best-effort 触发 plot/factor/overlay 的 sidecar ingest（不应因 sidecar 失败而破坏写入）。
- 成功后会向 `/ws/market` 推送 `candle_closed`（订阅该 `series_id` 的连接）。

## POST /api/market/ingest/candle_forming

### 示例请求（curl）

```bash
curl --noproxy '*' -sS -X POST "http://127.0.0.1:8000/api/market/ingest/candle_forming" \
  -H 'content-type: application/json' \
  -d '{"series_id":"binance:futures:BTC/USDT:1m","candle":{"candle_time":1700000060,"open":1,"high":2,"low":0.5,"close":1.6,"volume":12}}'
```

### 示例请求体（json）

```json
{
  "series_id": "binance:futures:BTC/USDT:1m",
  "candle": {"candle_time": 1700000060, "open": 1, "high": 2, "low": 0.5, "close": 1.6, "volume": 12}
}
```

### 示例响应（json）

```json
{"ok": true, "series_id": "binance:futures:BTC/USDT:1m", "candle_time": 1700000060}
```

### 语义

- 这是 **debug-only** 的 forming 推送入口：只有在 `TRADE_CANVAS_ENABLE_DEBUG_API=1` 时可用，否则返回 404。
- forming 只用于 UI 展示，不落库、不进入因子链路，但会向 `/ws/market` 推送 `candle_forming`。

## GET /api/market/whitelist

### 示例（curl）

```bash
curl --noproxy '*' -sS "http://127.0.0.1:8000/api/market/whitelist"
```

### 示例响应（json）

```json
{
  "series_ids": [
    "binance:futures:BTC/USDT:1m"
  ]
}
```

### 语义

- 返回服务端允许 ingest/订阅的 `series_id` 清单（真源见配置文件；用于前端 UI 列表与输入校验）。

## GET /api/market/debug/ingest_state

### 示例（curl）

```bash
curl --noproxy '*' -sS "http://127.0.0.1:8000/api/market/debug/ingest_state"
```

### 示例响应（json）

```json
{
  "note": "debug snapshot (structure may change)",
  "jobs": [],
  "subscriptions": {}
}
```

### 语义

- 仅在 `TRADE_CANVAS_ENABLE_DEBUG_API=1` 时可用，否则返回 404。
- 返回 ingest supervisor 的调试快照（该结构不承诺稳定；仅用于排障）。

## GET /api/market/debug/series_health

### 示例（curl）

```bash
curl --noproxy '*' -sS \
  "http://127.0.0.1:8000/api/market/debug/series_health?series_id=binance:futures:BTC/USDT:5m&max_recent_gaps=5&recent_base_buckets=8"
```

### 示例响应（json）

```json
{
  "series_id": "binance:futures:BTC/USDT:5m",
  "timeframe_seconds": 300,
  "now_time": 1700000000,
  "first_time": 1699995000,
  "head_time": 1699999800,
  "lag_seconds": 200,
  "candle_count": 1440,
  "gap_count": 1,
  "max_gap_seconds": 900,
  "recent_gaps": [
    {
      "prev_time": 1699996200,
      "next_time": 1699997100,
      "delta_seconds": 900,
      "missing_candles": 2
    }
  ],
  "base_series_id": "binance:futures:BTC/USDT:1m",
  "base_bucket_completeness": [
    {
      "bucket_open_time": 1699997400,
      "expected_minutes": 5,
      "actual_minutes": 5,
      "missing_minutes": 0
    }
  ]
}
```

### 语义

- 仅在 `TRADE_CANVAS_ENABLE_DEBUG_API=1` 时可用，否则返回 404。
- 用于排查 K 线链路健康度：给出 head 滞后、间隙统计、以及高周期相对 1m 基准桶的完整性。
- `max_recent_gaps` 控制返回最近 gap 条数；`recent_base_buckets` 控制最近多少个高周期桶做基准分钟完整性检查。

## GET /api/market/top_markets

### 示例（curl）

```bash
curl --noproxy '*' -sS \
  "http://127.0.0.1:8000/api/market/top_markets?exchange=binance&market=spot&quote_asset=USDT&limit=5"
```

### 示例响应（json）

```json
{
  "exchange": "binance",
  "market": "spot",
  "quote_asset": "USDT",
  "limit": 5,
  "generated_at_ms": 1700000000000,
  "cached": true,
  "items": [
    {
      "exchange": "binance",
      "market": "spot",
      "symbol": "BTC/USDT",
      "symbol_id": "binance:spot:BTC/USDT",
      "base_asset": "BTC",
      "quote_asset": "USDT",
      "last_price": 68000,
      "quote_volume": 123456789,
      "price_change_percent": 1.23
    }
  ]
}
```

### 语义

- 后端统一代理市场列表：避免前端直连交易所导致 CORS/口径漂移。
- `force=1` 会触发强制刷新，但有频率限制，可能返回 429（rate_limited）。
- 上游失败会返回 502（`upstream_error:*`）。

## GET /api/market/top_markets/stream

### 示例（curl / SSE）

```bash
curl --noproxy '*' -N \
  "http://127.0.0.1:8000/api/market/top_markets/stream?exchange=binance&market=spot&quote_asset=USDT&limit=5&interval_s=2&max_events=2"
```

### 示例响应（SSE data 部分是 json）

```json
{
  "exchange": "binance",
  "market": "spot",
  "quote_asset": "USDT",
  "limit": 5,
  "generated_at_ms": 1700000000000,
  "cached": true,
  "items": []
}
```

### 语义

- SSE 会以 `event: top_markets` 推送 payload，`id:` 为 `generated_at_ms`。
- 连接断开由服务端检测 `request.is_disconnected()`，并会定期发送 `: ping ...` keep-alive 注释行。
- 出错会推 `event: error`，`data` 为 `{"type":"error",...}`。
