---
title: API v1 · Plot（HTTP）
status: deprecated
created: 2026-02-03
updated: 2026-02-04
---

# API v1 · Plot（HTTP）

说明：`/api/plot/delta` 为历史遗留接口，**已废弃但仍保留兼容**；新代码应统一使用 `GET /api/draw/delta`。

## GET /api/plot/delta

> Deprecated：仅用于兼容旧链路；新实现请改用 `GET /api/draw/delta`。

### 示例（curl）

```bash
curl --noproxy '*' -sS \
  "http://127.0.0.1:8000/api/plot/delta?series_id=binance:futures:BTC/USDT:1m&cursor_candle_time=0&window_candles=2000"
```

### 示例响应（json）

```json
{
  "schema_version": 1,
  "series_id": "binance:futures:BTC/USDT:1m",
  "to_candle_id": "binance:futures:BTC/USDT:1m:1700000000",
  "to_candle_time": 1700000000,
  "lines": {},
  "overlay_events": [
    {
      "id": 1,
      "kind": "marker",
      "candle_id": "binance:futures:BTC/USDT:1m:1700000000",
      "candle_time": 1700000000,
      "payload": {"time": 1700000000, "text": "example"}
    }
  ],
  "next_cursor": {"candle_time": 1700000000, "overlay_event_id": 1}
}
```

### 语义

- 这是 plot 侧的增量接口（历史兼容口径）：主要返回 `overlay_events`（以及未来可扩展的 `lines`）。
- cursor 有两种：
  - `cursor_overlay_event_id`：按事件 id 增量（更稳定）
  - `cursor_candle_time`：按 candle_time 窗口拉取（用于首次/无 event_id 时）
- `next_cursor` 用于下一次增量请求；前端应持久化并用于“追到头”的判断。
