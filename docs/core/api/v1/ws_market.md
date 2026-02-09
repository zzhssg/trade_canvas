---
title: API v1 · Market WS
status: draft
created: 2026-02-03
updated: 2026-02-08
---

# API v1 · Market WS

## WS /ws/market

### 示例（wscat）

```bash
# 需要 node 工具：npm i -g wscat
wscat -c "ws://127.0.0.1:8000/ws/market"
```

### 示例消息（json）

```json
{"type":"subscribe","series_id":"binance:futures:BTC/USDT:1m","since":1700000000,"supports_batch":true}
```

### 语义

- 连接建立后必须先 `subscribe`，否则服务端只会对未知消息类型返回 error。
- `since`（可选）用于 catchup：服务端会先推送历史 closed candles，再继续推送实时 closed/forming。
- `supports_batch=true` 时，catchup 会用 `candles_batch` 一次性下发；否则逐根下发 `candle_closed`。
- gap 检测：若发现时间跳跃，服务端会发送 `{"type":"gap",...}`，用于提示前端补拉/重连。
- 若开启 `TRADE_CANVAS_ENABLE_MARKET_GAP_BACKFILL=1`，服务端在订阅 catchup 发现 gap 时会先尝试回补（best-effort），无法补齐才发送 `gap`。

### 服务端下行消息示例（json）

```json
{"type":"candles_batch","series_id":"binance:futures:BTC/USDT:1m","candles":[{"candle_time":1700000000,"open":1,"high":2,"low":0.5,"close":1.5,"volume":10}]}
```

```json
{"type":"candle_closed","series_id":"binance:futures:BTC/USDT:1m","candle":{"candle_time":1700000060,"open":1,"high":2,"low":0.5,"close":1.6,"volume":12}}
```

```json
{"type":"candle_forming","series_id":"binance:futures:BTC/USDT:1m","candle":{"candle_time":1700000120,"open":1,"high":2,"low":0.5,"close":1.7,"volume":13}}
```

```json
{"type":"gap","series_id":"binance:futures:BTC/USDT:1m","expected_next_time":1700000120,"actual_time":1700000240}
```
