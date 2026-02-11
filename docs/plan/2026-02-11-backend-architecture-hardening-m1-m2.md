---
title: 后端架构加固（M1+M2）
status: 待验收
owner: codex
created: 2026-02-11
updated: 2026-02-11
---

## 背景

后端架构评审发现两类可回滚的高收益改造点：
1. replay/overlay package 服务存在大量重复编排逻辑，后续演进有漂移风险；
2. factor 读链路在非 strict 模式仍会触发隐式重算，读写边界不够稳定。

## 目标 / 非目标

### 目标
- M1：抽取 package 构建共性基类，复用 `build/status` 作业状态编排。
- M2：新增 `TRADE_CANVAS_ENABLE_READ_IMPLICIT_RECOMPUTE` 开关（默认关闭），把非 strict 隐式重算收口为显式兼容模式。
- 保持现有 API 契约与路径不变，变更可通过开关或 `git revert` 回滚。

### 非目标
- 本轮不调整实时 WS 主链路发布流程（单独里程碑处理）。
- 本轮不改动 factor 算法语义（pivot/pen/zhongshu/anchor）。

## 方案概述

1. 新增 `package_build_service_base.py`，统一封装：
   - build job 预留（cache 命中 / 已有 job / 新建 job）
   - 状态决议（build_required / building / done / error）
   - 后台构建线程的 done/error 回写
2. `ReplayPackageServiceV1` 与 `OverlayReplayPackageServiceV1` 继承该基类，去掉重复状态机代码。
3. `RuntimeFlags` 新增 `enable_read_implicit_recompute`；
   - `container.py` 注入 `FactorReadService`
   - `factor_read_freshness.py` 仅在该开关为 true 时，非 strict 执行 `ensure_factor_fresh_for_read`。
4. 用测试锁定新语义与回归边界。

## E2E 用户故事（门禁）

- 角色：研究员
- 目标：在读链路默认只读的前提下，读取 factor/draw/world 一致快照。
- 流程：
  1) ingest `binance:futures:BTC/USDT:1m` 两根 candle（`1700000000`, `1700000060`）；
  2) 非 strict 且 `TRADE_CANVAS_ENABLE_READ_IMPLICIT_RECOMPUTE=0` 时读取 `/api/factor/slices`；
  3) 验证读取成功且不触发隐式重算；
  4) 开启 `TRADE_CANVAS_ENABLE_READ_IMPLICIT_RECOMPUTE=1` 再读，验证兼容重算路径可显式启用。
- 断言：
  - strict 模式 stale 因子仍返回 `409 ledger_out_of_sync:factor`；
  - implicit_recompute 开关在 runtime/container/read service 三层一致；
  - replay/overlay package 状态机语义与现有 API 保持一致。

## 里程碑

- M1：package 构建共性抽取（base + 两个 service 接入）
- M2：read implicit recompute kill-switch 收口

## 任务拆解

- [x] 新增 `backend/app/package_build_service_base.py`
- [x] 改造 `backend/app/replay_package_service_v1.py` 复用基类
- [x] 改造 `backend/app/overlay_package_service_v1.py` 复用基类
- [x] 新增 `TRADE_CANVAS_ENABLE_READ_IMPLICIT_RECOMPUTE`（`runtime_flags.py`）
- [x] 注入 `FactorReadService` 并收口非 strict 隐式重算逻辑
- [x] 补齐回归测试（base/read/runtime/container wiring）
- [x] 跑门禁并附证据

## 风险与回滚

- 风险：
  - package service 状态编排重构可能引入状态分支偏差；
  - 关闭隐式重算后，依赖旧行为的调用可能观察到“读取不补算”。
- 回滚：
  - 行为回滚：设置 `TRADE_CANVAS_ENABLE_READ_IMPLICIT_RECOMPUTE=1`；
  - 代码回滚：按里程碑 commit 执行 `git revert <sha>`。

## 验收标准

- `pytest -q backend/tests/test_package_build_service_base.py`
- `pytest -q backend/tests/test_replay_package_v1.py backend/tests/test_replay_overlay_package_api.py`
- `pytest -q backend/tests/test_factor_read_freshness.py backend/tests/test_factor_read_service.py backend/tests/test_runtime_flags.py backend/tests/test_backend_architecture_flags.py`
- `python3 -m mypy backend/app/package_build_service_base.py backend/app/replay_package_service_v1.py backend/app/overlay_package_service_v1.py backend/app/factor_read_freshness.py backend/app/read_models/factor_read_service.py backend/app/runtime_flags.py backend/app/container.py`
- `bash docs/scripts/doc_audit.sh`

## 变更记录

- 2026-02-11：创建计划并进入开发中（M1+M2）。
- 2026-02-11：完成 M1+M2 实现与回归门禁，进入待验收。
