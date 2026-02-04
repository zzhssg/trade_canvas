---
title: 市场币种列表（Binance Spot/Futures Top20）
status: draft
created: 2026-02-02
updated: 2026-02-02
---

# 市场币种列表（Binance Spot/Futures Top20）

目标：在 trade_canvas 的 Market 面板提供“可用且可解释”的币种列表入口，并满足：

- **现货（spot）**：展示 Binance 24h 交易量 Top 20
- **合约（futures / USDT-M）**：展示 Binance 24h 交易量 Top 20
- 与 `docs/core/market-kline-sync.md` 的 `series_id` 口径一致（exchange/market/symbol/timeframe 可组合成稳定标识）

本设计“批判性继承”自 `trade_system` 的核心口径：**只继承术语/不变量，不继承实现细节**。

---

## 1. 术语与不变量（必须一致）

### 1.1 `symbol`（UI / series 层）

- 形态：`BASE/QUOTE`（例如 `BTC/USDT`）
- 用途：作为 `series_id` 的组成部分（见 3.2）

### 1.2 `symbolId`（交易所 API 层）

- Binance 的标识：不带 `/` 的交易对（例如 `BTCUSDT`）
- UI 层永远使用 `symbol`，上游请求/路由才使用 `symbolId`

### 1.3 `market`（市场模式）

- `spot`：现货
- `futures`：合约（当前仅 USDT-M perpetual）

> 说明：trade_system 中常见命名为 `market_mode`；trade_canvas 侧简化为 `market`，但语义一致。

---

## 2. 数据源（Binance 公共接口）

### 2.1 Spot

- `exchangeInfo`：拿到 `baseAsset/quoteAsset/status`
- `ticker/24hr`：拿到 `lastPrice/quoteVolume/priceChangePercent`

### 2.2 Futures（USDT-M）

- `exchangeInfo`：过滤 `status=TRADING` 且 `contractType=PERPETUAL`
- `ticker/24hr`：同上

### 2.3 交易量口径（为何默认只取 USDT pairs）

Binance 返回的 `quoteVolume` 单位是 **quote 资产**。为了避免“不同 quote 资产之间不可比”，MVP 默认只展示：

- `quoteAsset == "USDT"`

后续如需“全市场 Top20”，需要引入统一折算口径（例如把 quoteVolume 折算为 USD 计价）。

---

## 3. 与 K 线同步的契约对齐

### 3.1 Market List 输出模型（前端）

对应实现：`frontend/src/services/useTopMarkets.ts`

- `exchange="binance"`
- `market in ("spot"|"futures")`
- `symbol="BASE/QUOTE"`（UI 统一口径）

### 3.2 `series_id` 对齐

与 `docs/core/market-kline-sync.md` 保持一致：

```
series_id = "{exchange}:{market}:{symbol}:{timeframe}"
```

Market list 负责提供 `exchange/market/symbol` 三元组；`timeframe` 由 UI/策略侧选择。

---

## 4. MVP 行为（可验收）

1) 在 Market 面板能切换 `spot/futures`，并分别展示 Top20（按 `quoteVolume` 倒序）。
2) 点击列表条目会更新当前选择的 `market + symbol`（供后续 series/订阅链路使用）。
3) 支持刷新（绕过短缓存），默认带短 TTL 防抖。

---

## 4.1 后端统一代理（推荐路径）

为了避免浏览器直连交易所导致的 CORS/网络策略风险，并统一口径与缓存，推荐前端只调用后端：

- `GET /api/market/top_markets?exchange=binance&market=spot&quote_asset=USDT&limit=20`
- `GET /api/market/top_markets?exchange=binance&market=futures&quote_asset=USDT&limit=20`

契约详见：`docs/core/contracts/market_list_v1.md`。

---

## 5. 归档：关键逻辑与踩坑点

### 5.1 “Top20”口径的陷阱：`quoteVolume` 不可跨 quote 资产直接比较

- `ticker/24hr.quoteVolume` 的单位是 **quote 资产**（例如 BTC/USDT 是 USDT，BTC/FDUSD 是 FDUSD）。
- 如果把所有交易对混在一起做 Top20，会出现“不同币种单位不可比”的伪排序。
- 因此 MVP 只取 `quoteAsset=="USDT"`（可比、且对业务足够用）。

### 5.2 Spot/Futures 都是“全量 ticker 拉回再筛”

- `/ticker/24hr` 返回的是全市场 ticker（数量较大），前端每次拉取会有体感延迟与带宽开销。
- 当前用短 TTL 缓存（默认 45s）+ 手动 Refresh 绕过缓存，属于“够用但不极致”的折中。
- 若要更实时/更省带宽：建议换成 Binance WS（miniTicker/ticker stream），在前端/后端增量维护 Top20。

### 5.3 Futures 合约范围要写死：只取 `PERPETUAL`

- Futures `exchangeInfo` 里可能包含多种 `contractType`，MVP 只保留 `PERPETUAL`，避免把交割合约混进“实盘列表”。

### 5.4 前端直连 Binance 的 CORS/可用性风险

- 开发期通过 Vite proxy（`/binance-spot`、`/binance-fapi`）规避 CORS。
- 生产环境如果直接从浏览器请求 `https://api.binance.com`/`https://fapi.binance.com`，可能因 CORS/网络策略不可用。
- 生产建议：由后端提供统一的 market list API（或反向代理），前端只打自家域名。

### 5.5 Symbol 口径：UI 用 `BASE/QUOTE`，请求层用 `symbolId`

- UI 与 `series_id` 统一用 `BTC/USDT` 形式，避免和“交易所内部 symbol”绑定。
- 请求/订阅（以后接 WS/K 线）再使用 `BTCUSDT` 这类 `symbolId`。
