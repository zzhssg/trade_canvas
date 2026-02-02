---
title: Market List Contract v1（Top Markets）
status: draft
created: 2026-02-02
updated: 2026-02-02
---

# Market List Contract v1（Top Markets）

目标：统一“市场币种列表”的数据结构与 HTTP API，使前端只依赖 trade_canvas backend，而不是直连交易所。

与 `docs/core/market-kline-sync.md` 对齐：market list 提供 `exchange/market/symbol` 三元组；K 线链路再补齐 `timeframe` 形成 `series_id`。

---

## 1. 术语

- `exchange`：交易所（当前仅 `binance`）
- `market`：`spot` | `futures`（futures 当前仅 USDT-M perpetual）
- `symbol`：`BASE/QUOTE`（例如 `BTC/USDT`）
- `symbol_id`：交易所原始 id（Binance：`BTCUSDT`）
- `quote_volume`：24h 成交额（单位为 quote 资产；因此默认按 `quote_asset=USDT` 才可比）

---

## 2. HTTP API

### 2.1 获取 Top Markets

`GET /api/market/top_markets`

Query:
- `exchange`：默认 `binance`
- `market`：`spot` 或 `futures`（必填）
- `quote_asset`：默认 `USDT`
- `limit`：默认 `20`，范围 `1..200`
- `force`：默认 `false`；为 `true` 时强制绕过缓存（受后端限流保护）

Response:
```json
{
  "exchange": "binance",
  "market": "spot",
  "quote_asset": "USDT",
  "limit": 20,
  "generated_at_ms": 1700000000000,
  "cached": true,
  "items": [
    {
      "exchange": "binance",
      "market": "spot",
      "symbol": "BTC/USDT",
      "symbol_id": "BTCUSDT",
      "base_asset": "BTC",
      "quote_asset": "USDT",
      "last_price": 100.0,
      "quote_volume": 123456789.0,
      "price_change_percent": 1.23
    }
  ]
}
```

约束：
- `items` 按 `quote_volume` 倒序。
- `cached=true` 表示本次命中后端缓存（或上游失败时返回缓存）。
- `force=true` 可能返回 `429 rate_limited`（避免把后端当压力工具）。

---

## 3. 失败语义（最小）

- `400 unsupported exchange`：exchange 不支持
- `429 rate_limited`：强制刷新过频
- `502 upstream_error:*`：交易所请求失败且无可用缓存

---

## 4. SSE（服务端推送）

当希望“列表更实时且避免轮询”时，使用 SSE：

`GET /api/market/top_markets/stream`

Query:
- `exchange/market/quote_asset/limit`：同 2.1
- `interval_s`：推送检查间隔（默认 2s；服务端可能在数据无变化时不重复推送）

事件：
- `event: top_markets`：`data` 为与 2.1 相同结构的 JSON（包含 `items`）
- `event: error`：上游异常（用于前端提示/回退）

说明：
- SSE 为单向（server→client），用于“榜单推送”非常合适；需要订阅/交互时再用 WS。
