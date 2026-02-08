---
title: API v1 · World（HTTP）
status: draft
created: 2026-02-03
updated: 2026-02-07
---

# API v1 · World（HTTP）

## GET /api/frame/live

### 示例（curl）

```bash
curl --noproxy '*' -sS \
  "http://127.0.0.1:8000/api/frame/live?series_id=binance:futures:BTC/USDT:1m&window_candles=2000"
```

### 示例响应（json）

```json
{
  "schema_version": 1,
  "series_id": "binance:futures:BTC/USDT:1m",
  "time": {"at_time": 1700000005, "aligned_time": 1700000000, "candle_id": "binance:futures:BTC/USDT:1m:1700000000"},
  "factor_slices": {"schema_version": 1, "series_id": "binance:futures:BTC/USDT:1m", "at_time": 1700000000, "candle_id": "binance:futures:BTC/USDT:1m:1700000000", "factors": [], "snapshots": {}},
  "draw_state": {"schema_version": 1, "series_id": "binance:futures:BTC/USDT:1m", "to_candle_id": "binance:futures:BTC/USDT:1m:1700000000", "to_candle_time": 1700000000, "active_ids": [], "instruction_catalog_patch": [], "series_points": {}, "next_cursor": {"version_id": 0, "point_time": null}}
}
```

### 语义

- live frame 是“当前最新对齐的世界状态”投影：由 `factor/slices + draw/delta` 组合而成。
- 字段命名对齐说明：当前 HTTP 返回字段为 `draw_state`（`WorldStateV1`），其语义等价于 `ReplayFrameV1` 里的 `draw_delta`。
- fail-safe：若 `factor_slices.candle_id` 与 `draw_state.to_candle_id` 不一致，返回 `409 ledger_out_of_sync`，禁止生成漂移 frame。

## GET /api/frame/at_time

### 示例（curl）

```bash
curl --noproxy '*' -sS \
  "http://127.0.0.1:8000/api/frame/at_time?series_id=binance:futures:BTC/USDT:1m&at_time=1700000005&window_candles=2000"
```

### 示例响应（json）

```json
{
  "schema_version": 1,
  "series_id": "binance:futures:BTC/USDT:1m",
  "time": {"at_time": 1700000005, "aligned_time": 1700000000, "candle_id": "binance:futures:BTC/USDT:1m:1700000000"},
  "factor_slices": {"schema_version": 1, "series_id": "binance:futures:BTC/USDT:1m", "at_time": 1700000000, "candle_id": "binance:futures:BTC/USDT:1m:1700000000", "factors": [], "snapshots": {}},
  "draw_state": {"schema_version": 1, "series_id": "binance:futures:BTC/USDT:1m", "to_candle_id": "binance:futures:BTC/USDT:1m:1700000000", "to_candle_time": 1700000000, "active_ids": [], "instruction_catalog_patch": [], "series_points": {}, "next_cursor": {"version_id": 0, "point_time": null}}
}
```

### 语义

- 点查 frame：服务端会将 `at_time` floor 到 closed 对齐时间后计算，返回的 `time.aligned_time` / `time.candle_id` 必须一致。
- fail-safe：同 live，一旦 slices 与 draw 的对齐不一致，直接 409 拒绝（避免“画对了但算错了 / 算对了但链路断了”）。

## GET /api/delta/poll

### 示例（curl）

```bash
curl --noproxy '*' -sS \
  "http://127.0.0.1:8000/api/delta/poll?series_id=binance:futures:BTC/USDT:1m&after_id=0&limit=2000&window_candles=2000"
```

### 示例响应（json）

```json
{
  "schema_version": 1,
  "series_id": "binance:futures:BTC/USDT:1m",
  "records": [
    {
      "id": 1,
      "series_id": "binance:futures:BTC/USDT:1m",
      "to_candle_id": "binance:futures:BTC/USDT:1m:1700000000",
      "to_candle_time": 1700000000,
      "draw_delta": {"schema_version": 1, "series_id": "binance:futures:BTC/USDT:1m", "to_candle_id": "binance:futures:BTC/USDT:1m:1700000000", "to_candle_time": 1700000000, "active_ids": [], "instruction_catalog_patch": [], "series_points": {}, "next_cursor": {"version_id": 1, "point_time": null}},
      "factor_slices": null
    }
  ],
  "next_cursor": {"id": 1}
}
```

### 语义

- v1 world delta 的增量游标是 `after_id`，当前实现把它映射到 draw 的 `version_id`（compat projection）。
- 每次 poll 最多返回 1 条 record：当 cursor 没前进时 `records=[]`，`next_cursor.id` 保持不变。

## POST /api/replay/prepare

### 示例（curl）

```bash
curl --noproxy '*' -sS -X POST \
  "http://127.0.0.1:8000/api/replay/prepare" \
  -H "Content-Type: application/json" \
  -d '{"series_id":"binance:futures:BTC/USDT:1m","to_time":1700000005,"window_candles":2000}'
```

### 示例请求（json）

```json
{"series_id":"binance:futures:BTC/USDT:1m","to_time":1700000005,"window_candles":2000}
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

- 受开关保护：`TRADE_CANVAS_ENABLE_REPLAY_V1=1` 时可用；关闭时返回 `404 not_found`。
- replay prepare 会确保 factor/overlay ledger 已补算并落库到 `aligned_time`，否则返回 409。
- `aligned_time` 为回放加载的对齐时间（close candle）。
