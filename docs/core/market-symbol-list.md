---
title: 市场币种列表（设计备忘，已合并至 market_list_v1）
status: deprecated
created: 2026-02-02
updated: 2026-02-09
---

# 市场币种列表（已合并）

本文档的契约/API 部分已合并至 `docs/core/contracts/market_list_v1.md`。

保留以下踩坑备忘供参考：

---

## 踩坑备忘

### `quoteVolume` 不可跨 quote 资产直接比较

- `ticker/24hr.quoteVolume` 的单位是 **quote 资产**（例如 BTC/USDT 是 USDT，BTC/FDUSD 是 FDUSD）。
- 如果把所有交易对混在一起做 Top20，会出现"不同币种单位不可比"的伪排序。
- 因此 MVP 只取 `quoteAsset=="USDT"`（可比、且对业务足够用）。

### Spot/Futures 都是"全量 ticker 拉回再筛"

- `/ticker/24hr` 返回的是全市场 ticker（数量较大），前端每次拉取会有体感延迟与带宽开销。
- 当前用短 TTL 缓存（默认 45s）+ 手动 Refresh 绕过缓存，属于"够用但不极致"的折中。

### Futures 合约范围要写死：只取 `PERPETUAL`

- Futures `exchangeInfo` 里可能包含多种 `contractType`，MVP 只保留 `PERPETUAL`，避免把交割合约混进"实盘列表"。

### Symbol 口径：UI 用 `BASE/QUOTE`，请求层用 `symbolId`

- UI 与 `series_id` 统一用 `BTC/USDT` 形式，避免和"交易所内部 symbol"绑定。
- 请求/订阅（以后接 WS/K 线）再使用 `BTCUSDT` 这类 `symbolId`。
