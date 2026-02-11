---
title: Market List Contract v1（Top Markets）
status: done
created: 2026-02-02
updated: 2026-02-11
---

# Market List Contract v1（Top Markets）

目标：统一市场币种列表的数据结构与 HTTP/SSE 协议，前端只依赖 trade_canvas backend，不直接耦合交易所细节。

与 `docs/core/market-kline-sync.md` 对齐：market list 提供 `exchange/market/symbol` 三元组；K 线链路再补齐 `timeframe` 形成 `series_id`。

---

## 1. 术语

- `exchange`：交易所（当前仅 `binance`）
- `market`：`spot` | `futures`（futures 当前仅 USDT-M perpetual）
- `symbol`：`BASE/QUOTE`（例如 `BTC/USDT`）
- `symbol_id`：交易所原始 id（例如 `BTCUSDT`）
- `quote_volume`：24h 成交额（单位为 quote 资产）

---

## 2. HTTP API

### 2.1 获取 Top Markets

`GET /api/market/top_markets`

Query:
- `exchange`：默认 `binance`
- `market`：`spot` 或 `futures`（必填）
- `quote_asset`：默认 `USDT`
- `limit`：默认 `20`，范围 `1..200`
- `force`：默认 `false`；`true` 时强制绕过缓存（受后端限流保护）

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
- `cached=true` 表示命中缓存（或上游失败时回退缓存）。
- `force=true` 可能返回 `429 rate_limited`。

---

## 3. SSE API

`GET /api/market/top_markets/stream`

Query：
- `exchange/market/quote_asset/limit`：同 HTTP
- `interval_s`：推送检查间隔（默认 2s）

事件：
- `event: top_markets`：data 与 2.1 相同
- `event: error`：上游异常信息

---

## 4. 失败语义（最小集合）

- `400 unsupported exchange`
- `429 rate_limited`
- `502 upstream_error:*`

---

## 5. 数据源与过滤规则

- Spot：`exchangeInfo` + `ticker/24hr`
- Futures（USDT-M）：`exchangeInfo`（过滤 `PERPETUAL`）+ `ticker/24hr`
- 默认 `quoteAsset=USDT` 以保证 `quote_volume` 可比

---

## 6. 踩坑约束（仍然有效）

1. `quoteVolume` 不能跨 quote 资产直接比较。
2. futures 必须过滤 `contractType=PERPETUAL`，避免混入交割合约。
3. UI 展示用 `BASE/QUOTE`，请求层再用 `symbol_id`。
