---
title: backend architecture hardening r5-r7 three round
status: 待验收
owner: codex
created: 2026-02-11
updated: 2026-02-12
---

## 背景

当前后端已经完成 M1-M4 的结构收敛，但架构评审仍有三类高收益问题：
1) 账本对齐/刷新流程分散在多个服务，重复逻辑多且行为容易漂移；
2) 实时 ingest 后台循环（supervisor/ws ingest）缺少可控熔断与退避策略，异常时容易表现为“死循环”；
3) 仍存在兼容层与组合根过重问题（兼容别名、重复协议定义、单文件依赖工厂过胖）。

本计划按三轮完成“最终架构收口”，每轮都可独立验收与回滚。

## 目标 / 非目标

### 目标
- R1：收敛 ledger 对齐/refresh 为单一服务，消除重复实现。
- R2：为 ingest 后台循环增加统一重试策略、熔断保护与可观测状态。
- R3：清理兼容层与重复协议，拆薄依赖组合根，落地最终口径。

### 非目标
- 不改动核心 factor 算法规则（pivot/pen/zhongshu/anchor）。
- 不新增对外协议字段（HTTP/WS payload schema 保持不变）。
- 不在本轮引入新的交易执行能力（仅做后端架构加固）。

## 方案概述

### R1（账本对齐单点化）
- 新增 `LedgerSyncService`，统一承载：
  - 对齐时间解析（requested/aligned）
  - refresh_series_sync 调度
  - factor/overlay head 就绪校验
- 将 `ReplayPrepareService`、`ReadRepairService`、`MarketLedgerWarmupService`、`startup_kline_sync` 的同类流程改为复用该服务。
- 首轮灰度曾引入开关：`TRADE_CANVAS_ENABLE_LEDGER_SYNC_SERVICE`；后续已在 2026-02-12 收口为强制单路径并移除。

### R2（ingest 循环熔断与退避）
- 抽取 supervisor/job 重试策略对象，统一 crash 计数、退避间隔、最大重试预算。
- 为 `IngestSupervisor` 与 `ingest_binance_ws` 增加：
  - 指数退避
  - 短窗 crash budget
  - 熔断状态（OPEN/HALF_OPEN/CLOSED）快照
- 新增开关：`TRADE_CANVAS_ENABLE_INGEST_LOOP_GUARDRAIL`（默认 `0`）。

### R3（去兼容层 + 组合根拆薄）
- 删除 processor/plugin 迁移兼容别名与包装导出（保留最终 tick plugin 口径）。
- 抽取共享协议 ports（DebugHub/HeadStore/IngestPipeline 等），移除重复 Protocol 定义。
- 拆分 `dependencies.py` 为按上下文的依赖模块（market/read/replay/dev），`main.py` 保持仅装配。

## 里程碑

- R1：LedgerSyncService 落地并接入 4 条读链路/修复链路。
- R2：ingest guardrail 落地，异常恢复策略可观测、可控制。
- R3：兼容层清理完成，依赖组合根拆薄并通过全量门禁。

## 任务拆解
- [x] R1 新增 ledger sync 服务并替换重复逻辑调用点
- [x] R1 新增并接入 `TRADE_CANVAS_ENABLE_LEDGER_SYNC_SERVICE`（历史阶段）
- [x] R2 抽取 ingest loop 重试/熔断策略并接入 supervisor + ws ingest
- [x] R2 新增 `TRADE_CANVAS_ENABLE_INGEST_LOOP_GUARDRAIL` 与 debug snapshot 输出
- [x] R3 删除 factor 兼容别名/包装，测试与文档全部切换最终口径
- [x] R3 抽取 shared ports 并删除重复 Protocol
- [x] R3 拆分 dependencies 组合根并保持路由注入契约不变
- [x] 三轮都补齐回归测试、执行全量门禁、同步文档状态

## 风险与回滚

- 风险：
  - R1 收敛后若对齐语义偏差，可能导致 replay/repair/warmup 行为变化。
  - R2 熔断策略若阈值配置不当，可能误伤实时 ingest 吞吐。
  - R3 去兼容层会影响存量 import 路径与测试引用。
- 回滚：
  - 运行时回滚：
    - `TRADE_CANVAS_ENABLE_INGEST_LOOP_GUARDRAIL=0`
  - 代码回滚：三轮分别独立 commit，支持 `git revert <sha>` 单轮回退。

## 验收标准

- R1：
  - `pytest -q backend/tests/test_replay_prepare_service.py backend/tests/test_read_repair_service.py backend/tests/test_market_ledger_warmup_service.py backend/tests/test_startup_kline_sync.py`
- R2：
  - `pytest -q backend/tests/test_ingest_supervisor.py backend/tests/test_ingest_binance_ws.py backend/tests/test_market_debug_routes.py`
- R3：
  - `pytest -q backend/tests/test_factor_registry.py backend/tests/test_factor_default_components.py backend/tests/test_app_state_boundary.py`
- 全量：
  - `pytest -q`
  - `python3 -m mypy backend/app`
  - `E2E_BACKEND_PORT=18080 E2E_FRONTEND_PORT=15180 bash scripts/e2e_acceptance.sh -- --grep "@mainflow"`
  - `bash docs/scripts/doc_audit.sh`

## E2E 用户故事（门禁）

### Story ID / E2E Test Case（必须）
- Story ID：`2026-02-11/backend-hardening-r5-r7/mainflow-consistency`
- 关联 Plan：`docs/plan/2026-02-11-backend-architecture-hardening-r5-r7-three-round.md`
- E2E 测试用例：
  - Test file path: `frontend/e2e/market_mainflow_comprehensive.spec.ts`
  - Test name(s): `mainflow comprehensive: ingest -> frame -> ws -> factor stays consistent @mainflow`
  - Runner：Playwright

### Persona / Goal
- Persona：研究员
- Goal：确认同一份 closed candle 输入在账本对齐、读模型与前端展示上保持一致，且重复读取可复现。

### Entry / Exit（明确入口与出口）
- Entry：
  - `series_id=binance:futures:TCMAINFLOW.../USDT:1m`
  - 顺序写入 closed candles：`1700000000`, `1700000060`, `1700000120`, `1700000180`
- Exit：
  - `/api/frame/live` 返回 `time.candle_id=<series_id>:1700000180`
  - `/api/factor/slices` 与 `/api/frame/at_time` 在 `1700000180` 上一致
  - 前端图表 `data-last-time=1700000180` 且 `data-last-close=44`

### Main Flow（主流程步骤 + 断言）
1) Step: 预置并写入 4 根 closed candle
   - Requests: `POST /api/market/ingest/candle_closed`
   - Assertions: `server_head_time` 最终为 `1700000180`
   - Evidence: Playwright API response + backend 日志
2) Step: 打开 `/live` 并建立 ws 订阅
   - Requests: `GET /api/frame/live` + `WS /ws/market subscribe`
   - Assertions: 收到 `candle_closed` 的 `candle_time=1700000180`
   - Evidence: e2e trace + ws payload snapshot
3) Step: 重复读取一致性
   - Requests: 连续两次 `GET /api/factor/slices?at_time=1700000180`
   - Assertions: 两次 JSON 完全一致，`candle_id` 均为 `<series_id>:1700000180`
   - Evidence: e2e test assertion output

### Produced Data（产生的数据）
- `candles` 表：`series_id/candle_time/open/high/low/close/volume`
- `factor_events` + `factor_head_snapshots`：读链路一致性基线
- `overlay_instruction_versions`：draw/world 对齐输出

### Verification Commands（必须可复制运行）
- `E2E_BACKEND_PORT=18080 E2E_FRONTEND_PORT=15180 bash scripts/e2e_acceptance.sh -- --grep "@mainflow"`
  - Expected：主链路测试通过，且 `1700000180` 的 candle/frame/slices 三方一致

### Rollback（回滚）
- 最短回滚：按轮次 `git revert`，并将两个新开关设为 `0`。

## 变更记录
- 2026-02-11: 创建（草稿）
- 2026-02-11: R1 完成（LedgerSyncService 接入 replay/repair/warmup/startup，增加 `TRADE_CANVAS_ENABLE_LEDGER_SYNC_SERVICE`）
- 2026-02-11: R2 完成（ingest loop guardrail 接入 supervisor + binance ws + debug snapshot，增加 `TRADE_CANVAS_ENABLE_INGEST_LOOP_GUARDRAIL`）
- 2026-02-11: R3 完成（移除 processor 兼容层、抽 shared ports、拆分 dependencies 模块）
- 2026-02-12: R1/R3 收口（移除 `TRADE_CANVAS_ENABLE_LEDGER_SYNC_SERVICE`，read/repair/warmup/startup 固定使用 LedgerSyncService 单路径）
