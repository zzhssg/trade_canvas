---
title: 后端质量一次性收敛（配置拆分 + 类型收口）
status: 开发中
owner: codex
created: 2026-02-14
updated: 2026-02-14
---

## 背景

当前后端测试通过，但存在三类阻断：
1. 结构门禁未满足（`Settings`/`RuntimeFlags` dataclass 字段超限）。
2. SR 因子路径存在 mypy 报错，类型契约漂移。
3. storage 层存在重复 helper 与 `Any` 扩散，维护成本偏高。

## 目标 / 非目标

### 目标
- 一次性消除后端高优先级质量问题，并恢复可复核门禁通过。
- 保持现有运行行为与 API 合同不变（同输入同输出）。
- 全程原子化改动，可按 commit 独立回滚。

### 非目标
- 不在本轮新增业务功能。
- 不做前端大规模重构。

## 方案概述

- 方案 A（采用）：将配置对象按领域拆分（嵌套 dataclass），同时保留只读访问路径，先过结构门禁，再做类型收口与重复治理。
- 方案 B（放弃）：仅加 ignore/临时判断快速消错；虽然快，但会保留结构债与后续返工风险。

取舍：方案 A 更符合可回滚、可验收、可持续演进（P2/P10/P14）。

## 里程碑

1. 落盘计划与 E2E 门禁故事。
2. 配置对象拆分并过结构门禁。
3. storage helper 收口，降低重复实现。
4. SR 路径类型修复并通过 mypy。
5. 统一门禁执行与证据留档。

## 任务拆解

- [x] 新增计划文档并固化 E2E 用户故事。
- [x] 拆分 `backend/app/core/config.py`：`Settings` -> 领域嵌套对象。
- [x] 拆分 `backend/app/runtime/flags.py`：`RuntimeFlags` -> 领域嵌套对象。
- [x] 新增 storage 公共 helper，替换重复实现。
- [x] 修复 `sr_analyzer` / `processor_sr` 的 mypy 报错。
- [x] 执行并记录门禁：`pytest -q backend/tests`、`mypy backend/app --pretty --no-error-summary`、`cd frontend && npm run build`、`bash scripts/quality_gate.sh`。
- [x] 收敛参数超限（>8）：`StoreBackfillService`、`WsSubscriptionCoordinator.handle_subscribe`、`IngestSupervisor` 改为对象参数。
- [x] 收敛 Postgres 存储类型覆盖噪音：引入 `DbConnection/DbCursor` 协议并移除 `PostgresFactorRepository`、`PostgresOverlayRepository` 的 override ignore。

## 风险与回滚

- 风险1：配置拆分导致读取路径失配。
  - 回滚：`git revert <config/flags commit>`。
- 风险2：storage helper 改动引入 Postgres 读取兼容问题。
  - 回滚：`git revert <storage commit>`。
- 风险3：SR 类型修复误改行为。
  - 回滚：`git revert <sr commit>`，并保留原测试对拍。

## 验收标准

- `backend/tests` 全绿。
- `mypy backend/app` 无报错。
- `quality_gate.sh` 通过。
- 结构门禁不再命中 dataclass 字段超限。

## E2E 用户故事（门禁）

### 用户故事
- 角色：量化研究员。
- 目标：新闭合 K 线进入后，`candles -> factor -> overlay -> world` 全链路对齐。

### 入口
- `series_id=binance:futures:BTC/USDT:1m`。
- 注入一批闭合 K 线（含具体 `candle_time`，如 `1735689600` 之后连续数据）。

### 主流程断言
1. ingest 写入成功，`/api/market/candles` 能读到新增尾部。
2. factor/overlay 同步推进，`/api/draw/delta` 游标前进。
3. `world/frame/live` 返回 `time.aligned_time` 与 `candle_id` 对齐。

### 证据命令
- `bash scripts/e2e_acceptance.sh`
- `pytest -q backend/tests/test_e2e_user_story_market_sync.py`

## 变更记录
- 2026-02-14: 创建并进入开发中。
- 2026-02-14: 完成配置/flags 拆分、SR 类型修复、storage helper 收口；后端门禁全绿。
- 2026-02-14: 完成 market/ingest 参数对象化，清零后端函数参数超限项（>8）。
- 2026-02-14: 完成 Postgres 存储类型契约收口，移除仓储层 override ignore 噪音。

## 验证记录（2026-02-14）

- `pytest -q` -> `451 passed`
- `pytest -q backend/tests/test_runtime_flags.py backend/tests/test_config_market_settings.py backend/tests/test_sr_factor.py` -> `18 passed`
- `pytest -q backend/tests/test_e2e_user_story_market_sync.py` -> `6 passed`
- `mypy backend/app --pretty --no-error-summary` -> `0 error`（仅 annotation-unchecked note）
- `bash scripts/quality_gate.sh` -> `OK`
- `bash docs/scripts/doc_audit.sh` -> `OK`
- `bash scripts/e2e_acceptance.sh` -> 失败（2 条现有前端 E2E 用例：`chart_wheel_behavior.spec.ts`、`market_kline_sync.spec.ts`）
- `pytest -q backend/tests/test_market_data_services.py backend/tests/test_ingest_supervisor_capacity.py backend/tests/test_ingest_supervisor_role_guard.py backend/tests/test_ingest_supervisor_whitelist_fallback.py backend/tests/test_market_ws.py backend/tests/test_market_runtime_routes.py` -> `34 passed`
- `pytest -q backend/tests/test_pg_only_connection_compat.py backend/tests/test_postgres_schema_bootstrap.py backend/tests/test_backend_architecture_flags.py backend/tests/test_market_data_services.py backend/tests/test_market_runtime_routes.py` -> `41 passed`
