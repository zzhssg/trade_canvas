---
title: 市场 K 线同步（Whitelist 实时 + 非白名单按需补齐）
status: draft
created: 2026-02-02
updated: 2026-02-09
---

# 市场 K 线同步（Whitelist 实时 + 非白名单按需补齐）

目标：让 **因子引擎（策略）** 与 **前端图表** 消费同一套 `CandleClosed` 真源，并在资源可控的前提下实现：

1) **白名单内币种**：后台持续 ingest，保证实时性（闭合后尽快可用）。  
2) **白名单外币种**：只有当用户在前端查看时，才触发“历史增量补齐 + WS 实时跟随”。

本设计“批判性继承”自 `trade_system` 的核心口径（只继承契约/术语/不变量，不继承实现细节）：
- `closed` 为权威输入，`forming` 仅用于显示。
- 使用稳定坐标 `candle_time`（Unix seconds）作为跨窗口/跨 seek 的主键；`idx` 仅允许作为局部窗口编号（如需要）。
- append-only 事件流优先，避免全量重算与语义漂移。

参考来源（仅供对齐术语/不变量）：  
`../trade_system/user_data/doc/Core/核心架构.md`、`../trade_system/user_data/doc/Core/术语与坐标系（idx-time-offset）.md`

---

## 0. 关键术语（必须一致）

### 0.1 CandleSeries（K 线序列）

一条序列由下列维度唯一确定：
- `exchange`（例如 `binance`）
- `market`（例如 `spot` / `futures`，可选）
- `symbol`（例如 `BTC/USDT`）
- `timeframe`（例如 `1m` / `5m`）

建议派生一个稳定标识：
- `series_id = "{exchange}:{market}:{symbol}:{timeframe}"`（或等价确定性表示）

### 0.2 CandleClosed（闭合 K）

闭合 K 的权威字段（最小集合）：
- `candle_time`：K 线开盘时间（Unix seconds，整齐对齐 timeframe 边界）
- `open/high/low/close/volume`

稳定主键（用于所有下游对齐与去重）：
- `candle_id = "{series_id}:{candle_time}"`

> 说明：这里把 trade_canvas 的 `candle_id={symbol}:{timeframe}:{open_time}` 扩展成带 `exchange/market` 的 `series_id`，避免多交易所/多市场冲突。

### 0.3 Forming（未闭合 K）

`forming` 仅用于图表“当前 K 的动态更新”，必须满足：
- 不进入因子引擎与策略信号
- 不落库为权威历史

---

## 1. 总体架构（同源双轨）

同一条 `CandleClosed` 事件流，分叉出两条消费：
- **策略/因子**：增量更新产出 `ledger`（策略读取的最新指标/信号）
- **图表**：增量更新产出 `overlay`（绘图指令）

市场 K 线同步本身只负责：**把 `CandleClosed` 稳定、可补齐、可订阅地提供给上述两条链路**。

### 1.1 模块收口目标（Phase A，契约先行）

为降低当前 K 线逻辑分散在 `main.py` / `ws_hub.py` / 各类 backfill 脚本的治理成本，v1 先在
`backend/app/market_data/contracts.py` 统一定义领域能力契约，不改线上行为：

- `CandleReadService`：一次性读取 / 增量读取 / 区间读取（只读 closed）。
- `BackfillService`：gap 回补与 tail 覆盖（best-effort）。
- `FreshnessService`：序列新鲜度判定（missing/fresh/stale/degraded）。
- `WsDeliveryService`：WS 订阅阶段 catchup 与 gap 修复策略。
- `MarketDataOrchestrator`：面向 API/WS 的总编排入口。

后续 Phase B/C 仅允许在该契约边界内迁移实现，避免继续在路由层和 hub 层散落同类逻辑。

### 1.2 收口进度（Phase B，读链路先迁）

当前已完成第一步行为保持型迁移（不改 HTTP/WS 对外契约）：
- `GET /api/market/candles` 的读取入口改为经 `MarketDataOrchestrator.read_candles(...)`。
- WS 订阅 catchup 的读取与 gap-heal 调度改为经 `MarketDataOrchestrator`。
- `FreshnessService` 负责提供 `head_time/lag/state` 快照，路由层不再直接拼装新鲜度口径。

### 1.3 收口进度（Phase C，gap 回补集中化）

当前已把 `gap -> best-effort backfill -> 区间回读` 从路由内联逻辑迁移到 `market_data`：
- `StoreBackfillService.backfill_gap(...)` 统一承接 gap 回补（含 kill-switch）。
- `StoreBackfillService.ensure_tail_coverage(...)` 支持按 `to_time` + `target_candles` 评估覆盖窗口。
- `build_gap_backfill_handler(...)` 统一封装 WS gap 回补处理器并注入 `CandleHub`。
- `main.py` 不再内联 gap 回补细节，仅负责装配 `reader/backfill/orchestrator`。

### 1.4 收口进度（Phase D，derived 首次回填集中化）

当前已把“订阅 derived 序列时的首次历史回填（best-effort）”从 `main.py` 内联逻辑迁移到 `market_data`：
- `build_derived_initial_backfill_handler(...)` 统一封装 derived 首次回填流程（开关判定 + rollup + sidecar）。
- `main.py` 在 WS subscribe 前仅调用 handler，不再直接处理 derived 的回填细节。
- 回填后仍保持既有行为：按 `rebuilt` 决定是否 reset overlay，再 ingest overlay。

### 1.5 收口进度（Phase E，WS catchup 协调集中化）

当前已把 WS subscribe 中 `since / last_sent / catchup / gap-heal` 的协调逻辑集中到 `market_data`：
- `MarketDataOrchestrator.build_ws_catchup(...)` 统一处理 catchup 过滤与 gap-heal。
- 为保持并发语义，路由层仍先 read、后取 `last_sent`，再把 read 结果交给 orchestrator 汇总。
- 路由层只保留 WS 协议编解码与发包，不再拼装 catchup 过滤细节。

### 1.6 收口进度（Phase F，WS catchup 发包策略集中化）

当前已把 WS catchup 的发包策略（`gap + candles_batch/candle_closed`）集中到 `market_data`：
- `MarketDataOrchestrator.build_ws_emit(...)` 统一构造 WS payload 队列与 `last_sent_time`。
- 路由层只做 `send_json` 循环与 `hub.set_last_sent(...)` 一次性更新。
- 批量/逐条两条路径的消息结构保持不变（兼容现有客户端）。

### 1.7 收口进度（Phase G，订阅协同集中化）

当前已把 WS subscribe 中“ondemand 容量判定 + hub 订阅/退订协同”抽到 `market_data`：
- `WsSubscriptionCoordinator.subscribe(...)` 统一处理：容量判定失败时返回标准 `capacity` 错误 payload；成功时执行 hub 订阅。
- `WsSubscriptionCoordinator.unsubscribe(...)` 统一处理 ondemand/hub 退订协同。
- 路由层不再直接拼装 `capacity` 错误结构，减少协议漂移点。

### 1.8 收口进度（Phase H，断线清理协同集中化）

当前已把 WS 断线后的清理逻辑（`hub.pop_ws + ondemand refcount release`）从路由层抽到 `market_data`：
- `WsSubscriptionCoordinator.cleanup_disconnect(...)` 统一处理断线后订阅集合合并与 ondemand 退订。
- 路由层 finally 仅调用一次 cleanup，不再内联循环释放逻辑。
- 断线清理异常对主链路保持 best-effort（逐条保护，避免放大故障）。

### 1.9 收口进度（Phase I，订阅状态本地化到 Coordinator）

当前已把 WS 路由里的 `subscribed_series` 本地状态管理下沉到 `WsSubscriptionCoordinator`：
- coordinator 内部维护 ws→series 集合，并在 subscribe/unsubscribe 时增删。
- `cleanup_disconnect(...)` 使用“coordinator 本地集合 ∪ hub.pop_ws”统一释放，不再依赖路由传参。
- 路由层进一步收敛为协议编解码与单点调用。

---

## 2. Part A：白名单内币种（保证实时性）

### 2.1 行为目标

对白名单内的 `(series_id)`：
- 后台持续 ingest（无需前端有人查看）
- 保证闭合 K 线在“可接受延迟”内进入本地真源（store），并可通过 API/WS 消费

> “实时性”在这里的工程定义：`candle_close_time + grace_window` 之后，`CandleClosed(candle_time)` 必须可被查询到。`grace_window` 由实现配置（例如 3~10 秒，取决于交易所与网络）。

### 2.2 数据链路（建议）

1) **启动/重启补洞**：对每个白名单 `series_id`，从 store 的 `last_candle_time` 开始向上游补齐缺口（REST fetch），直到接近当前时间。
2) **持续 ingest**：订阅交易所 websocket/stream（或轮询）获取闭合 K 线；写入 store（幂等 upsert）。
3) **对外广播**：写入成功后向 WS 广播 `candle_closed`（保证顺序以 `candle_time` 为准）。

### 2.3 幂等与顺序不变量

- 幂等：同一 `candle_id` 重复写入必须安全（写入层去重/覆盖同版本）。
- 顺序：对外输出（API/WS）按 `candle_time` 单调递增；发现 gap 必须显式告知（见 4.3）。

### 2.4 Whitelist 真源（v1 先用文件）

Whitelist（白名单 `series_id` 列表）的真源位置：
- `backend/config/market_whitelist.json`

服务端可通过 `GET /api/market/whitelist` 暴露当前白名单（用于前端/运维自检）。

白名单常驻 ingest 通过环境变量启用：
- `TRADE_CANVAS_ENABLE_WHITELIST_INGEST=1`
- 当 `TRADE_CANVAS_ENABLE_WHITELIST_INGEST=0` 时，白名单币种在“被订阅”后会自动走 ondemand ingest（避免默认 BTC/USDT 出现“已订阅但不更新”）。

---

## 3. Part B：按需补齐 + WS 跟随（含白名单回退场景）

### 3.1 目标与边界

对“按需模式”中的 `(series_id)`（非白名单，或白名单但常驻 ingest 关闭）：
- **不承诺后台持续实时 ingest**
- 当且仅当“前端有人查看/订阅”时，触发补齐与短期实时跟随
- 无人订阅时允许停更（节省资源）

### 3.2 前端同步流程（推荐）

1) **HTTP 拉取（增量补齐）**
   - 前端首次加载默认拉取最近 **2000** 根：`GET /api/market/candles?series_id=...&limit=2000`（不带 `since`）
   - 增量补齐：`GET /api/market/candles?series_id=...&since=<last_candle_time>&limit=...`
   - 服务端从 store 返回按 `candle_time` 排序的 `CandleClosed[]` 与 `server_head_time`（当前已知最新闭合 time）。
   - 前端循环请求直到 `last_received_time >= server_head_time`（增量补齐完成）。

2) **建立 WS 并订阅（实时跟随）**
   - WS 连接后发送：`subscribe { series_id, since=last_received_time }`
   - 服务端从 `since`（不含/含由协议定义）开始推送后续 `candle_closed`。

3) **服务端按需 ingest（仅订阅期）**
   - 当检测到某 `series_id` 第一次有人订阅：启动该序列的 ingest worker（先补洞到 head，再跟随实时）。
   - 当订阅数归零并超过 `idle_ttl`：停止该序列 ingest（释放资源）。

v1 实现建议（后端开关）：
- `TRADE_CANVAS_ENABLE_ONDEMAND_INGEST=1`
- `TRADE_CANVAS_ONDEMAND_IDLE_TTL_S=<seconds>`（默认 60）

### 3.3 单一上游实时源 + 多周期派生（Derived Timeframes）

动机：上游实时源（例如 Binance WS）通常以 `1m` 的频率最稳定；为了避免“每个 timeframe 各起一条 ingest job”，引入 **从 base(1m) 派生多周期** 的能力：

- 仅连接 `...:1m` 的上游 WS（单一上游连接）
- 在服务端对 `5m/15m/1h/4h/1d` 做二次加工
- **forming 仅用于展示**：只走 `WS /ws/market`，不落库、不进入因子/策略
- **closed 为权威输入**：派生周期的 `CandleClosed` 落库（独立 `series_id`），并触发因子/overlay 的增量计算

开关（默认关闭，便于回滚）：
- `TRADE_CANVAS_ENABLE_DERIVED_TIMEFRAMES=1`：启用派生
- `TRADE_CANVAS_DERIVED_BASE_TIMEFRAME=1m`：基准周期（v1 固定 1m）
- `TRADE_CANVAS_DERIVED_TIMEFRAMES=5m,15m,1h,4h,1d`：派生周期集合（缺省值与前端默认集合对齐，且排除 base）

订阅行为（重要）：
- 当客户端订阅派生 `series_id`（例如 `...:5m`）且派生能力启用：
  - supervisor 会把订阅映射到 base `...:1m` 管理 refcount / job 生命周期（避免再起一条 5m 的上游 ingest）
  - 派生 `forming/closed` 由服务端从 base 1m 流中 fanout 得到，并按派生 `series_id` 推送给客户端

首次订阅回填（best-effort）：
- 若客户端首次订阅派生 `series_id`，且本地 store 中该派生序列尚无历史：
  - 服务端可从本地 base(1m) tail 派生一段派生 closed 回填（只要 base 有足够闭合分钟）
  - 目的：让图表能“立即渲染”并尽快进入实时跟随
- 缺口/断线：派生周期的闭合要求“桶内分钟齐全”；若 base 丢分钟导致派生桶无法闭合，应通过 `gap` 显式暴露并回退到 HTTP 增量补齐。

---

## 4. API / WS 协议（最小 v1）

### 4.1 HTTP：增量读取（建议接口）

`GET /api/market/candles`

Query:
- `series_id`（必填）
- `since`：起始 `candle_time`（可选；缺省为“从最早可用处/或按 limit 向前”）
- `limit`：分页大小（必填，服务端可上限）

Response（示例）：
```json
{
  "series_id": "binance:futures:BTC/USDT:1m",
  "server_head_time": 1700000000,
  "candles": [
    {"candle_time": 1699999940, "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 100}
  ]
}
```

约束：
- `candles` 按 `candle_time` 升序
- `server_head_time` 表示“服务端当前已落库/已知的最新闭合 candle_time”

### 4.2 WS：订阅与推送（建议消息）

Client → Server：
- `hello { client, version }`（可选）
- `subscribe { series_id, since, supports_batch? }`
- `unsubscribe { series_id }`

Server → Client：
- `candle_closed { series_id, candle }`
- `candles_batch { series_id, candles[] }`（可选：当 client 声明 `supports_batch=true` 时，用于 catchup/回填批量下发）
- `gap { series_id, expected_next_time, actual_time }`（发现缺口/乱序时）
- `error { code, message }`

补充约束：
- `supports_batch` 缺省为 `false`（服务端对旧客户端保持逐条 `candle_closed` 兼容）
- `candles_batch.candles` 必须按 `candle_time` 升序；客户端应去重后合并到本地序列（以 `candle_time` 为主键）

### 4.3 Gap 处理（必须有明确策略）

当服务端发现：
- `actual_time > expected_next_time`（缺口）
- 或客户端订阅时 `since` 落后太多导致丢包风险

服务端应发送 `gap`，客户端必须回退到 HTTP 增量补齐再继续订阅。

可选增强（默认关闭，便于回滚）：
- `TRADE_CANVAS_ENABLE_MARKET_GAP_BACKFILL=1`：在 WS 订阅 catchup 发现 gap 时，服务端先做 best-effort 补齐，再决定是否发送 `gap`。
- 与 `TRADE_CANVAS_ENABLE_CCXT_BACKFILL=1` 组合时，服务端会在本地/freqtrade 补齐不足时尝试 CCXT 回补缺口区间。

---

## 5. 资源与限流（建议）

为防止“非白名单被刷爆”：
- 限制同时活跃的非白名单 ingest worker 数量（例如按 LRU 淘汰）
- 限制单连接可订阅的 series 数量
- `limit` 上限与分页速率限制

---

## 6. MVP 验收（可验证）

### 6.1 白名单实时性（最小）

- 给定一个白名单 `series_id`，持续运行 10 分钟：
  - `server_head_time` 单调递增
  - WS `candle_closed` 的 `candle_time` 不乱序、不重复（允许幂等重复但客户端去重后应严格单调）

### 6.2 非白名单按需补齐（最小）

- 前端首次打开非白名单 `series_id`：
  - 先通过 HTTP 把历史补齐到 `server_head_time`
  - 再通过 WS 继续收到后续 `candle_closed`
- 关闭页面（unsubscribe）超过 `idle_ttl` 后：
  - 后台停止该 `series_id` 的实时 ingest（可通过日志/指标验证）

---

## 附：前端图表对接注意事项（轻量图表库）

- `lightweight-charts@5` 中 series **没有** `setMarkers`，markers 需要使用 `createSeriesMarkers(series)` 返回的 plugin API（`setMarkers([...])`）。
- 图表尺寸变化（例如拖动底部高度）应通过 `chart.applyOptions({ width, height })` 更新；不要在 resize 时频繁 `createChart/remove`，否则更容易出现“数据已在 state，但新 chart 尚未 setData”的空图体验。
