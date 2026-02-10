---
title: backend architecture hardening v2
status: 待验收
owner:
created: 2026-02-10
updated: 2026-02-10
---

## 背景

后端在近期迭代后已经可用，但存在 4 类结构性风险：
- 写链路在 `HTTP/WS/replay` 三处重复实现，异常处理策略不一致；
- 读接口隐式触发写入（factor/overlay auto ingest），难以保证读路径无副作用；
- `main.py` 装配过重，`app.state` 承载过多服务定位器职责；
- 高风险开关分散在多处 `os.environ`，上线灰度和回滚成本偏高。

本计划目标是在不破坏既有契约的前提下，一次性完成 M0-M3 全量硬化，并通过开关保持可回滚。

## 目标 / 非目标

### 目标
- 引入统一 `IngestPipeline`，收敛 closed-candle 主写链路；
- 引入读模型 `FactorReadService`，支持 strict 模式下读写分离；
- 引入 `AppContainer + FeatureFlags`，统一装配与主链路开关治理；
- 保持现有 HTTP/WS 契约兼容，默认行为不破坏（新能力默认关闭）。

### 非目标
- 不改动前端接口结构与字段名；
- 不重写 `FactorOrchestrator` / `OverlayOrchestrator` 内部算法；
- 不在本轮移除所有 `os.environ` 读取，只覆盖主链路关键路径。

## 方案概述

### M0 文档与门禁落盘
- 新增本计划文档并绑定 worktree；
- 同步更新 `docs/core/architecture.md`、`docs/core/factor-modular-architecture.md`。

### M1 统一写链路（`IngestPipeline`）
- 新增 `backend/app/pipelines/ingest_pipeline.py`；
- HTTP `POST /api/market/ingest/candle_closed`、Binance WS ingest、Replay Ensure Coverage 统一接入；
- 开关：`TRADE_CANVAS_ENABLE_INGEST_PIPELINE_V2=1` 时启用，默认关闭。

### M2 读写分离（strict read）
- 新增 `backend/app/read_models/factor_read_service.py`；
- `factor/draw/world` 读链路统一读服务；
- strict 模式下禁止读路径自动重算，出现滞后返回 `409 ledger_out_of_sync:*`；
- 开关：`TRADE_CANVAS_ENABLE_READ_STRICT_MODE=1` 时启用，默认关闭。

### M3 容器化装配 + flags 集中治理
- 新增 `backend/app/container.py`、`backend/app/flags.py`；
- `main.py` 切换为容器装配，保留兼容 `app.state.*` 暴露；
- `market_runtime` 显式携带 `flags + ingest_pipeline`，减少散落读取。

## 里程碑

### M0（文档与计划）
- 改什么：`docs/plan/2026-02-10-backend-architecture-hardening-v2.md` + `docs/core/*`
- 怎么验收：`bash docs/scripts/doc_audit.sh`
- 怎么回滚：`git revert <doc-commit>`

### M1（统一写链路）
- 改什么：`backend/app/pipelines/*` + `market_http_routes.py` + `ingest_binance_ws.py` + `replay_package_service_v1.py`
- 怎么验收：`pytest -q backend/tests/test_market_runtime_routes.py backend/tests/test_replay_package_v1.py`
- 怎么回滚：`TRADE_CANVAS_ENABLE_INGEST_PIPELINE_V2=0`

### M2（读写分离）
- 改什么：`backend/app/read_models/*` + `factor_routes.py` + `draw_routes.py` + `world_routes.py`
- 怎么验收：`pytest -q backend/tests/test_factor_read_service.py backend/tests/test_draw_delta_api.py backend/tests/test_world_state_frame_api.py`
- 怎么回滚：`TRADE_CANVAS_ENABLE_READ_STRICT_MODE=0`

### M3（容器与开关治理）
- 改什么：`backend/app/container.py` + `backend/app/main.py` + `backend/app/flags.py`
- 怎么验收：`pytest -q backend/tests/test_market_runtime_routes.py backend/tests/test_config_market_settings.py`
- 怎么回滚：`git revert <container-commit>` 或临时回退到 `main.py` 旧装配分支

## 任务拆解
- [x] 落盘计划并绑定 worktree
- [x] 新增 `IngestPipeline` 并接入 HTTP/WS/Replay
- [x] 新增 `FactorReadService` 并接入 factor/draw/world 读链路
- [x] 新增 `AppContainer + FeatureFlags` 并切换 `main.py` 装配
- [x] 运行全量后端测试与文档审计
- [x] 更新 plan 状态为 `待验收`

## 风险与回滚

- 风险 1：新写链路异常策略变严导致行为变化  
  回滚：关闭 `TRADE_CANVAS_ENABLE_INGEST_PIPELINE_V2`，恢复旧路径。
- 风险 2：strict 模式导致旧“读触发写”依赖失效  
  回滚：关闭 `TRADE_CANVAS_ENABLE_READ_STRICT_MODE`。
- 风险 3：容器装配引入状态注入遗漏  
  回滚：保留 `app.state` 兼容字段，并通过 `git revert` 回退容器改动。

## 验收标准

- 后端回归：`pytest -q backend/tests`
- 文档审计：`bash docs/scripts/doc_audit.sh`
- E2E 用户故事（见下方）跑通，且在 strict/v2 开关开启时返回预期状态码与一致性断言。

## E2E 用户故事（门禁）

### Persona / Goal
- Persona：量化研究员（后端 API 使用者）
- Goal：在同一 `series_id` 上验证“同一根 candle 的 market/factor/draw/world 一致对齐”，并验证 strict 模式不产生读副作用。

### 固定场景（具体数值）
- `series_id = binance:spot:BTC/USDT:1m`
- 依次写入 3 根 closed candle：
  - `1700000000` close=`100.0`
  - `1700000060` close=`101.5`
  - `1700000120` close=`99.8`

### 流程与断言
1. **写入闭环（HTTP）**  
   命令：连续 3 次 `POST /api/market/ingest/candle_closed`  
   断言：3 次均 `200`，最后一次 `candle_time=1700000120`。
2. **行情读取（market）**  
   命令：`GET /api/market/candles?series_id=...&since=1700000000&limit=10`  
   断言：返回时间序列 `[1700000060, 1700000120]`，`server_head_time=1700000120`。
3. **因子切片读取（factor）**  
   命令：`GET /api/factor/slices?series_id=...&at_time=1700000120&window_candles=2000`  
   断言：`candle_id == binance:spot:BTC/USDT:1m:1700000120`。
4. **绘图读取（draw）**  
   命令：`GET /api/draw/delta?series_id=...&cursor_version_id=0&at_time=1700000120`  
   断言：`to_candle_id == binance:spot:BTC/USDT:1m:1700000120`。
5. **世界帧一致性（world）**  
   命令：`GET /api/frame/at_time?series_id=...&at_time=1700000120`  
   断言：`world.time.candle_id == factor.candle_id == draw.to_candle_id`。
6. **strict 读写分离断言**  
   设置：`TRADE_CANVAS_ENABLE_READ_STRICT_MODE=1` 且故意制造 overlay/factor 落后  
   断言：`GET /api/draw/delta` / `GET /api/factor/slices` 返回 `409 ledger_out_of_sync:*`（不触发后台重算）。

## 变更记录
- 2026-02-10: 创建（草稿）
- 2026-02-10: 状态更新为开发中，确定 M0-M3 一次性执行方案
- 2026-02-10: 完成 M0-M3 代码实现与门禁，状态推进为待验收
