---
title: 企业级扩展：PostgreSQL + TimescaleDB + WS 横向扩容
status: 开发中
owner:
created: 2026-02-13
updated: 2026-02-13
---

## 背景

当前主链路已经满足“功能正确 + 可回放 + 可验收”，但容量模型仍偏单机：

- 数据真源为单机 SQLite（`candles/factor/overlay` 同库），核心实现位于：
  - `backend/app/store.py`
  - `backend/app/factor_store.py`
  - `backend/app/overlay_store.py`
- 实时分发与订阅状态为进程内内存（`CandleHub` + `WsSubscriptionCoordinator`），难以天然支持多实例广播：
  - `backend/app/ws_hub.py`
  - `backend/app/market_data/ws_services.py`
- 容量指标是进程内快照，缺少企业级统一监控与压测门禁。

目标场景：支持上千人只读看盘（不改参数），在不破坏现有 HTTP/WS 契约、不破坏 `closed candle` 主链路不变量前提下完成可回滚升级。

## 目标 / 非目标

### 目标（Do）

1. 引入 PostgreSQL（candles 采用 TimescaleDB hypertable）作为可水平扩展的数据底座。
2. 保持现有 API 契约与读模型语义稳定（`closed` 权威、`forming` 仅展示、读写分离）。
3. 支持多实例 WS 横向扩容：任一实例 ingest，所有实例订阅端都能收到同源增量。
4. 升级观测与门禁：提供可复现的容量验证（命令 + 指标 + 产物）。
5. 全程可回滚：所有新能力由 `TRADE_CANVAS_ENABLE_*` 开关控制，默认关闭。

### 非目标（Don't）

1. 不在一轮内“硬切”所有读取从 SQLite 到 PostgreSQL。
2. 不改现有外部 HTTP/WS 协议字段（仅可增加 debug/观测字段，且受开关保护）。
3. 不做参数编辑、多租户权限系统的完整产品化（本轮聚焦只读扩容主链路）。

## 方案概述

采用“双轨渐进 + 开关灰度”策略，分两条主线并行推进：

### 主线 A：数据层迁移（SQLite -> PostgreSQL/TimescaleDB）

- A1（准备态）：新增 PG/Timescale schema 与 repository 抽象，不改变线上读写路径。
- A2（镜像态，已废弃）：曾规划 `dual-write`，现已改为 PG single-write。
- A3（校验态）：引入对账与漂移检测（head_time/row_count/checksum），确保同输入同输出。
- A4（切读态）：按接口逐步切换读来源（先 market candles，再 factor/draw/world），每步可独立回滚。

#### M2 决策（2026-02-13）

- 已切换为 **B / PG single-write（硬切）**：
  - 移除 dual-write / pg-read 分叉，`TRADE_CANVAS_ENABLE_PG_STORE=1` 时 candles/factor/overlay 全部走 PG。
  - 移除 `DataReconcileService` 与 `/api/market/debug/reconcile`（不再维护 SQLite 对账语义）。
- 理由：
  - 当前项目未上线、可丢历史数据，优先最快清理旧路径；
  - 降低运行时复杂度与排障面，避免“双写+对账”长期残留。

#### M6 收官（2026-02-13）

- 已移除 SQLite 相关代码/开关/脚本路径，运行时不再支持 SQLite fallback。
- `TRADE_CANVAS_ENABLE_PG_STORE=0` 时默认使用本地内存 store（开发/测试），不依赖 sqlite 驱动。
- 新增零残留守卫，禁止 `TRADE_CANVAS_ENABLE_SQLITE_STORE` 与 `sqlite3` 回流到生产代码路径。

### 主线 B：实时层扩容（单进程内存广播 -> 跨实例 pub/sub）

- B1：新增 WS 发布适配层（保留当前内存实现）。
- B2：接入 Redis pub/sub（可替换为 NATS，但本轮默认 Redis）并提供 `TRADE_CANVAS_ENABLE_WS_PUBSUB`。
- B3：Web 节点无状态化；ingest 维持单活 worker（或受控少量 worker）避免重复上游抓取。

### 主线 C：观测与容量门禁

- C1：输出统一指标（ingest/query/ws + pubsub + db latency + backlog）。
- C2：新增容量脚本（1k 只读连接 smoke）与验收证据目录。
- C3：把容量门禁纳入交付（非通过不得宣称完成）。

## 一次性集成回合（已确认）

> 用户已确认采用“硬切最终架构 + 保留 kill-switch”路径。本计划按一次集成回合执行，不再按回合反复确认。

- Integrator: Codex（backend 集成回合）
- Touched: `backend/app/`, `backend/tests/`, `docs/core/`, `docs/plan/`, `scripts/`
- Gate:
  - `bash docs/scripts/api_docs_audit.sh --list`
  - `pytest -q backend/tests/test_postgres_schema_bootstrap.py backend/tests/test_ws_pubsub_scaleout.py backend/tests/test_e2e_user_story_market_scaleout.py`
  - `pytest -q`
  - `python3 -m mypy backend/app`
  - `cd frontend && npm run build`
  - `E2E_BACKEND_PORT=18080 E2E_FRONTEND_PORT=15180 TRADE_CANVAS_ENABLE_PG_STORE=1 TRADE_CANVAS_ENABLE_WS_PUBSUB=1 bash scripts/e2e_acceptance.sh`
  - `bash docs/scripts/doc_audit.sh`
- Evidence: `output/2026-02-13-scaleout-integrated/*`
- Rollback:
  - runtime: `TRADE_CANVAS_ENABLE_PG_STORE=0 TRADE_CANVAS_ENABLE_WS_PUBSUB=0`
  - code: `git revert <集成提交sha>`

### 一次性执行顺序（并行后仲裁）

1. **控制面与装配收口**：统一开关解析、容器装配、依赖导出（不改对外契约）。
2. **存储层落地**：补齐 local/postgres repository，并由 runtime builder 注入；随后移除 dual-write 分支。
3. **主链路切换**：ingest/read/ws 路径全部改走 repository + publisher 抽象。
4. **对账与观测**：补 reconcile service 与 debug API，固定证据输出。
5. **门禁与文档**：一次性跑全门禁，补齐 API/架构文档并归档证据。

## 里程碑

### M0：契约冻结与迁移基线（不改行为）

- 产出：迁移 plan、接口契约冻结清单、feature flags 草案、E2E 用户故事落盘。
- 验收：`pytest -q --collect-only` + `cd frontend && npx tsc -b --pretty false --noEmit`。
- 回滚：纯文档与开关草案，直接 `git revert`。

### M1：PostgreSQL/TimescaleDB 基础设施接入（默认关闭）

- 产出：PG 连接配置、schema bootstrap、`candles` hypertable、仓储接口。
- 验收：新增单测验证 schema 创建与基本读写；旧链路不受影响。
- 回滚：关闭 `TRADE_CANVAS_ENABLE_PG_STORE`，系统回到本地内存 store。

### M2：写链路收口（PG single-write）

- 产出：ingest/factor/overlay 统一写 PG，移除 dual-write/pg-read 分叉与 reconcile 调试接口。
- 验收：固定输入下 `head_time` 与历史读取一致，且主链路无 dual-write 依赖。
- 回滚：关闭 `TRADE_CANVAS_ENABLE_PG_STORE`。

### M3：WS pub/sub 横向扩容（默认关闭）

- 产出：`CandleHub` 发布适配层 + Redis bridge + 多实例广播一致性测试。
- 验收：双实例下，A 实例 ingest，B 实例连接的客户端收到 `candle_closed`。
- 回滚：关闭 `TRADE_CANVAS_ENABLE_WS_PUBSUB`，退回进程内广播。

### M4：读链路统一 PG（分步灰度）

- 产出：`/api/market/candles`、factor/draw/world 在 PG store 开启时统一走 PG 仓储。
- 验收：E2E 用户故事通过；同输入同输出保持稳定。
- 回滚：关闭 `TRADE_CANVAS_ENABLE_PG_STORE`，回退本地内存 store。

### M5：容量验收与交付

- 产出：容量报告（连接数、延迟、错误率、资源占用）+ 交付证据。
- 验收：`bash scripts/e2e_acceptance.sh` + 容量脚本达标。
- 回滚：任何不达标节点按开关降级，不影响主链路可用性。

## 任务拆解

### 1) 配置与开关（控制面）

- [x] 修改 `backend/app/config.py`
  - 新增 PG/Redis 配置读取（URL、pool、schema、timescale）。
- [x] 修改 `backend/app/runtime_flags.py`
  - 新增：
    - `TRADE_CANVAS_ENABLE_PG_STORE`
    - `TRADE_CANVAS_ENABLE_WS_PUBSUB`
    - `TRADE_CANVAS_ENABLE_CAPACITY_METRICS`

### 2) 数据层仓储抽象与实现

- [x] 新增 `backend/app/storage/contracts.py`
  - 定义 candle/factor/overlay repository 协议（避免路由/服务耦合存储细节）。
- [x] 新增 `backend/app/storage/postgres_*.py`
  - 实现 PG 对应仓储；`candles` 使用 Timescale hypertable。
- [x] 新增 `backend/app/storage/postgres_factor_repo.py`、`backend/app/storage/postgres_overlay_repo.py`
  - 为 `factor/overlay` 提供 PostgreSQL 仓储实现（支持 PG-only 模式）。
- [x] 修改 `backend/app/container.py`、`backend/app/market_runtime_builder.py`
  - 按开关装配 local/pg，且 PG store 开启时统一 single-write。
- [x] 修改 `backend/app/runtime_flags.py`
  - 增加 `TRADE_CANVAS_ENABLE_PG_ONLY`（开发阶段快速硬切主链路到 PostgreSQL）。

### 3) 写链路收口（PG single-write）

- [x] 修改 `backend/app/pipelines/ingest_pipeline.py`
  - 保留步骤语义，清理 dual-write 分支后主链路仅依赖单写仓储。
- [ ] 修改 `backend/app/factor_orchestrator.py`、`backend/app/overlay_orchestrator.py`
  - 输出写入委托到抽象仓储。
- [x] 删除 `backend/app/storage/dual_write_repos.py`、`backend/app/storage/sqlite_repos.py`
  - 移除 dual-write 与 storage 层 legacy alias。
- [x] 删除 `backend/app/data_reconcile_service.py`
  - 下线旧对账服务。
- [x] 修改 `backend/app/market_debug_routes.py`
  - 移除 `/api/market/debug/reconcile`，保留 debug ingest/series_health/metrics。

### 4) WS 横向扩容

- [x] 新增 `backend/app/ws_publishers/base.py`
  - 统一发布接口（memory/redis）。
- [x] 新增 `backend/app/ws_publishers/redis_publisher.py`
  - Redis pub/sub 实现。
- [x] 修改 `backend/app/ws_hub.py`、`backend/app/market_data/ws_services.py`
  - 接入发布适配层，保持现有订阅协议不变。
- [x] 修改 `backend/app/ingest_supervisor.py`
  - 加入多实例部署模式下的 ingest 角色约束（避免重复抓取）。

### 5) 测试与容量门禁

- [x] 新增 `backend/tests/test_ws_pubsub_scaleout.py`
- [x] 新增 `backend/tests/test_e2e_user_story_market_scaleout.py`
- [x] 新增 `scripts/load/ws_readonly_smoke.sh`（或等价脚本）
- [x] 新增 `output/capacity/` 证据落盘约定（日志、指标快照、图表）

## 风险与回滚

### 核心风险

1. **迁移残留漂移**：旧 SQLite 路径未完全清理，导致行为分叉或运维误判。
2. **WS 重复/丢消息**：跨实例 pub/sub 可能出现顺序问题或重复广播。
3. **吞吐回退**：PG 连接池/索引策略不当导致读写性能下降。
4. **运维复杂度提升**：引入 Redis + PG 后部署和排障复杂度上升。

### 回滚策略

- 数据层：
  - 关闭 `TRADE_CANVAS_ENABLE_PG_STORE`：读写回本地内存 store。
- 实时层：
  - 关闭 `TRADE_CANVAS_ENABLE_WS_PUBSUB`：回退到进程内 hub。
- 代码层：
  - 每个里程碑独立提交，均可单独 `git revert <sha>`。

## 验收标准

1. 功能一致性：主链路 E2E（ingest -> frame/live -> ws -> delta）通过。
2. 主链路一致性：在固定输入样本下，PG store 开启/关闭两种模式都可复现。
3. 容量指标：1k 只读连接 smoke 下，订阅成功率、消息送达率、p95 延迟达到目标阈值（阈值在执行阶段固化）。
4. 回滚可行性：任意阶段可通过开关或 `git revert` 在 10 分钟内恢复到 local-store + in-memory WS 路径。

## E2E 用户故事（门禁）

### Story ID / E2E Test Case（必须）

- Story ID：`2026-02-13/market/scaleout-readonly-1000-watchers`
- 关联 Plan：`docs/plan/2026-02-13-enterprise-scale-postgresql-timescaledb-and-ws-scaleout.md`
- E2E 测试用例：
  - Test file path: `backend/tests/test_e2e_user_story_market_scaleout.py`
  - Test name(s):
    - `test_dual_write_and_pg_read_consistency_under_scaleout_mode`
    - `test_multi_instance_ws_pubsub_delivers_closed_to_remote_subscribers`
  - Runner：`pytest`

### Persona / Goal

- Persona：只读看盘交易员（并发上千连接）。
- Goal：在多实例部署下持续看到最新 closed K，不出现漏推/错位。

### Entry / Exit（明确入口与出口）

- Entry：
  - 启动双实例 backend（A/B），开启 `DUAL_WRITE + WS_PUBSUB`。
  - 客户端连接 B 实例 `ws://.../ws/market` 并订阅 `binance:futures:BTC/USDT:1m`。
- Exit：
  - A 实例 ingest 新 closed candle 后，B 实例客户端收到同一 `candle_time` 的 `candle_closed`。
  - `/api/market/candles`（PG 读开关开启）返回的最后一根与 WS 消息一致。

### Concrete Scenario（必须：写“具体数值”，禁止空泛）

- Chart / Symbol:
  - series_id: `binance:futures:BTC/USDT:1m`
  - timezone: `UTC`
- Initial State：
  - DB empty?: yes（测试专用库）
  - Existing candles:
    - `candle_time=1700000000` o=100 h=101 l=99 c=100.5 v=10
    - `candle_time=1700000060` o=100.5 h=102 l=100 c=101.2 v=11
- Trigger Event：
  - POST `/api/market/ingest/candle_closed` 写入
    - `candle_time=1700000120` o=101.2 h=103 l=101 c=102.4 v=12
- Expected outcome：
  - WS：收到 `candle_closed.candle_time == 1700000120`
  - API：`/api/market/candles?since=1700000060` 返回最后一根 `candle_time == 1700000120`
  - 存储：PG `head_time == 1700000120`

### Preconditions（前置条件）

- 环境变量（显式固定）：
  - `TRADE_CANVAS_ENABLE_PG_STORE=1`
  - `TRADE_CANVAS_ENABLE_WS_PUBSUB=1`
- 依赖服务：PostgreSQL + TimescaleDB + Redis（测试容器）。

### Main Flow（主流程步骤 + 断言）

1) 建立订阅与初始 catchup
- User action：客户端连 B 实例并 subscribe。
- Requests：WS `subscribe` + HTTP `GET /api/market/candles`。
- Backend chain：`ws_services -> ws_hub -> store read`。
- Assertions：初始最后一根 `candle_time=1700000060`。
- Evidence：pytest 日志 + WS 抓包文本。

2) 由 A 实例写入 closed candle
- User action：调用 A 实例 ingest。
- Requests：`POST /api/market/ingest/candle_closed`（candle_time=1700000120）。
- Backend chain：`ingest_pipeline -> pg single-write -> ws publisher(redis)`。
- Assertions：API 返回 success；PG head 与返回数据一致。
- Evidence：接口响应、debug metrics。

3) B 实例订阅端接收增量
- User action：等待 B 实例 WS 消息。
- Requests：WS stream。
- Backend chain：`redis subscriber -> local hub -> ws send`。
- Assertions：收到 `candle_closed.candle_time=1700000120` 且仅一次。
- Evidence：pytest 断言日志、输出文件。

### Produced Data（产生的数据）

- Tables / Files:
  - `candles` hypertable（PostgreSQL/TimescaleDB）
  - `factor_events` / `overlay_instruction_versions`（PG）
- how to inspect:
  - PG：`SELECT max(candle_time) ...`
  - WS：测试日志与消息快照

### Verification Commands（必须可复制运行）

- `pytest -q backend/tests/test_ws_pubsub_scaleout.py backend/tests/test_e2e_user_story_market_scaleout.py`
  - Expected：两个用例全部通过；关键断言包含 `1700000120`。
- `cd frontend && npm run build`
  - Expected：前端契约构建通过。
- `bash scripts/e2e_acceptance.sh`
  - Expected：主链路 E2E 通过并生成 `output/...` 证据。

### Rollback（回滚）

- 最短回滚：
  - 关 `TRADE_CANVAS_ENABLE_PG_STORE` + `TRADE_CANVAS_ENABLE_WS_PUBSUB`
  - 回退到本地内存仓储 + in-memory WS 路径继续服务（仅开发/测试兜底）。

## 变更记录

- 2026-02-13: 创建（草稿）
- 2026-02-13: 补充企业级扩容迁移方案（PG/Timescale + WS scaleout + E2E 门禁）
- 2026-02-13: M1 起步实现（PG/Redis 配置、runtime 开关、Postgres schema bootstrap 与单测）
- 2026-02-13: M2 起步实现（local/postgres/dual-write candle repository、容器按开关注入、dual-write 回归测试）
- 2026-02-13: M2 收口实现（移除 dual-write/pg-read/reconcile 路径，PG store 启用后统一 single-write）
- 2026-02-13: M3 起步实现（ws publisher 抽象、Redis publisher、CandleHub pubsub bridge、scaleout 回归测试）
- 2026-02-13: M5 起步实现（ws readonly capacity smoke 脚本 + output/capacity 证据落盘约定）
- 2026-02-13: M2 收官（移除 backend/app SQLite 实现与 replay sqlite 包，replay 改为 JSON package）
- 2026-02-13: M6 收官（删除 `TRADE_CANVAS_ENABLE_SQLITE_STORE` 与脚本/测试残留，零残留守卫接入 quality gate）
