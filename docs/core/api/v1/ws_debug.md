---
title: API v1 · Debug WS
status: done
created: 2026-02-04
updated: 2026-02-11
---

# API v1 · Debug WS

## WS /ws/debug

### 示例（wscat）

```bash
# 需要 node 工具：npm i -g wscat
# 注意：仅在后端启用 TRADE_CANVAS_ENABLE_DEBUG_API=1 时可用
wscat -c "ws://127.0.0.1:8000/ws/debug"
```

### 客户端上行示例（json）

```json
{"type":"subscribe"}
```

### 服务端下行示例（json）

```json
{"type":"debug_snapshot","events":[{"ts_ms":1700000000123,"source":"backend","pipe":"read","event":"read.http.market_candles","series_id":"binance:futures:BTC/USDT:5m","level":"info","message":"get market candles","data":{"count":10,"last_time":1700000000}}]}
```

```json
{"type":"debug_event","event":{"ts_ms":1700000000456,"source":"backend","pipe":"write","event":"write.http.ingest_candle_closed_done","series_id":"binance:futures:BTC/USDT:5m","level":"info","message":"ingest candle_closed done","data":{"candle_time":1700000060,"duration_ms":12}}}
```

### 语义

- gate：当 `TRADE_CANVAS_ENABLE_DEBUG_API != 1` 时，服务端会拒绝/关闭连接。
- `debug_snapshot`：连接建立后服务端会先下发一次最近的 ring buffer（最多约 2000 条）。
- `debug_event`：后续实时推送新增事件。
- event 字段（稳定用于测试/断言）：
  - `pipe`: `read` / `write`
  - `event`: 稳定事件码（例如 `read.http.market_candles` / `write.http.ingest_candle_closed_done`）
  - `series_id`: 可选，用于定位某一条行情链路
