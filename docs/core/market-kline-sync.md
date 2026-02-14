---
title: 市场 K 线同步（当前实现）
status: done
created: 2026-02-02
updated: 2026-02-14
---

# 市场 K 线同步（当前实现）

本文只描述 **当前可运行实现**，不再保留阶段迁移日志。

目标：让 market 数据链路在“同输入同输出”前提下，同时满足：
- closed 数据可持续落库并驱动下游；
- forming 数据可用于 UI 实时展示；
- 白名单常驻 + 非白名单按需都能稳定工作。

---

## 1. 核心术语与不变量

### 1.1 序列标识

- `series_id = {exchange}:{market}:{symbol}:{timeframe}`
- `candle_id = {series_id}:{candle_time}`

### 1.2 数据语义

- `closed`：权威输入，允许落库并驱动 factor/overlay。
- `forming`：展示输入，仅广播，不落库，不参与因子/策略。

### 1.3 写链路顺序

固定顺序：`candles -> factor -> overlay -> publish`

统一执行器：`backend/app/pipelines/ingest_pipeline.py`

---

## 2. 模块职责

### 2.1 市场运行时装配

- `backend/app/market/runtime_builder.py`
- `backend/app/market/runtime.py`

职责：
- 组装 reader/backfill/ws/coordinator/supervisor。
- 绑定 `RuntimeFlags`（功能开关与运行参数统一收口）。
- 输出 `MarketRuntime` 给 HTTP/WS 路由复用。

### 2.2 市场数据子模块

目录：`backend/app/market_data/`

- `read_services.py`：读取、freshness、backfill 服务
- `orchestrator.py`：market_data 聚合编排
- `ws_services.py`：ws 消息解析与订阅协同
- `derived_services.py`：derived 首次回填处理

### 2.3 路由层

- HTTP：`backend/app/market/http_routes.py`、`backend/app/market/meta_routes.py`
- WS：`backend/app/market/ws_routes.py`

职责：
- 做协议输入输出与参数校验。
- 调用 runtime service，不承载复杂业务分支。

---

## 3. HTTP 链路

### 3.1 读 candles

接口：`GET /api/market/candles`

行为：
1. 可选自动 tail coverage（按开关触发）。
2. 调 `market_data.read_candles(...)` 返回 closed 列表。
3. 附带 `server_head_time` 供前端判断 catchup 是否追平。

### 3.2 写 closed/forming

- `POST /api/market/ingest/candle_closed`
  - 调 `MarketIngestService.ingest_candle_closed()`。
  - 最终进入 `IngestPipeline`。
- `POST /api/market/ingest/candle_forming`
  - debug-only（受 `enable_debug_api` 控制）。
  - 只广播 forming，不落库。

### 3.3 辅助接口

- `/api/market/whitelist`
- `/api/market/top_markets`
- `/api/market/top_markets/stream`
- `/api/market/debug/ingest_state`（debug-only）
- `/api/market/debug/series_health`（debug-only）
- `/api/market/health`（受健康灯开关控制）

---

## 4. WS 链路

```mermaid
sequenceDiagram
  participant Client as 前端
  participant Route as /ws/market
  participant Parser as WsMessageParser
  participant Coord as WsSubscriptionCoordinator
  participant Sup as IngestSupervisor
  participant Loop as Binance ingest loop
  participant Pipe as IngestPipeline
  participant Hub as CandleHub

  Client->>Route: subscribe(series_id, since)
  Route->>Parser: parse_subscribe
  Parser->>Coord: subscribe command
  Coord->>Sup: subscribe(refcount++)
  Sup->>Loop: ensure ingest job
  Loop->>Pipe: flush closed batch
  Pipe->>Hub: publish closed/forming/system
  Hub-->>Client: ws payload
```

关键点：
- parser 统一 bad_request/unknown type 错误语义。
- coordinator 统一 catchup + subscribe/unsubscribe + disconnect cleanup。
- supervisor 统一管理 whitelist/ondemand 生命周期。

---

## 5. 白名单与按需模式

### 5.1 白名单模式

开关：`RuntimeFlags.enable_whitelist_ingest`

- 启动时常驻 ingest 白名单序列。
- 无需前端订阅即可持续推进。

### 5.2 按需模式

开关：`RuntimeFlags.enable_ondemand_ingest`

- 首个订阅触发启动任务。
- refcount 归零后按 `ondemand_idle_ttl_s` 回收。
- `RuntimeFlags.ondemand_max_jobs` 可限制并发作业数。

### 5.3 启动巡检补齐（可选）

开关：`RuntimeFlags.enable_startup_kline_sync`

- 启动时可对 whitelist 序列做一次“到最新闭合时间”的巡检补齐。
- 每个序列会先跑 `ensure_tail_coverage(..., to_time=expected_latest_closed_time)`。
- 补齐后会触发一次 `ingest_pipeline.refresh_series_sync`，确保 factor/overlay 与 candle 同步推进。
- 目标窗口由 `RuntimeFlags.startup_kline_sync_target_candles` 控制。

---

## 6. Derived Timeframe 语义

开关：`RuntimeFlags.enable_derived_timeframes`

- base timeframe：`derived_base_timeframe`（默认 `1m`）
- derived 集合：`derived_timeframes`
- 首次回填窗口：`derived_backfill_base_candles`

语义：
- 订阅 derived 序列时，生命周期管理映射到 base job。
- derived forming/closed 从 base 流派生。
- derived closed 可落库并驱动 factor/overlay。

---

## 7. 配置真源（当前口径）

### 7.1 Env 解析工具（`backend/app/core/flags.py`）

- `env_bool` / `env_int` / `resolve_env_float` / `resolve_env_str`
- 仅负责解析环境变量，不承载业务语义

### 7.2 RuntimeFlags（`backend/app/runtime/flags.py`）

- 常用开关：
  - `enable_debug_api`
  - `enable_whitelist_ingest`
  - `enable_ondemand_ingest`
  - `enable_market_auto_tail_backfill`
  - `market_auto_tail_backfill_max_candles`
  - `ondemand_idle_ttl_s`
- 回补与历史源：
  - `enable_market_gap_backfill`
  - `market_gap_backfill_freqtrade_limit`
  - `enable_startup_kline_sync`
  - `startup_kline_sync_target_candles`
  - `enable_ccxt_backfill`
  - `enable_ccxt_backfill_on_read`
  - `market_history_source`
- derived：
  - `enable_derived_timeframes`
  - `derived_base_timeframe`
  - `derived_timeframes`
  - `derived_backfill_base_candles`
- ws 批处理：
  - `binance_ws_batch_max`
  - `binance_ws_flush_s`
  - `market_forming_min_interval_ms`
- 健康灯：
  - `enable_kline_health_v2`
  - `kline_health_backfill_recent_seconds`

---

## 8. 失败语义与排障入口

### 8.1 常见失败语义

- 订阅参数非法：`bad_request`
- on-demand 容量不足：`capacity`
- 链路不同步：`ledger_out_of_sync:*`

### 8.2 排障入口

1. `backend/app/market/ws_routes.py`
2. `backend/app/market_data/ws_services.py`
3. `backend/app/ingest/supervisor.py`
4. `backend/app/ingest/binance_ws.py`
5. `backend/app/pipelines/ingest_pipeline.py`
6. `backend/app/runtime/flags.py`

---

## 9. 已废弃认知

- 不再使用 `market_flags.py` 或独立 `FeatureFlags` 模块作为配置入口。
- 不再在 `main.py` 内联市场业务逻辑。
- 不再维护“阶段迁移日志式”文档作为实现真源。
