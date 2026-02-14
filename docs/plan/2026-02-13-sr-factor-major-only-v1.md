---
title: SR 因子 major-only v1（插件化 + 绘图 + 回放）
status: 开发中
owner: codex
created: 2026-02-13
updated: 2026-02-13
---

## 背景

现有因子链路已完成 pivot/pen/zhongshu/anchor 插件化，但 SR（水平线）尚未落地。目标是在不引入兼容层、不保留遗留双轨的前提下，把 SR 接入同一套 factor/overlay/replay 主链路。

## 目标 / 非目标

- 目标
  - 新增 `sr` 因子插件（依赖 `pivot.major`）
  - 新增 SR overlay 渲染插件（`sr.active` / `sr.broken`）
  - 前端 catalog/store/replay 对 `sr` 可见
  - 补齐回归测试与证据
- 非目标
  - 不做旧 SR 接口兼容
  - 不做 minor/major 混合策略（本轮只做 major-only）

## 方案概述

- 方案 A（已选）
  - major-only：仅消费 `pivot.major`，每次新 major 出现时生成 `sr.snapshot`。
  - 优点：契约稳定、改动集中、回滚成本低。
- 方案 B（未选）
  - major+minor 混合：更高灵敏度，但状态重建复杂、验收成本高。

## 里程碑

1. 落地 SR 因子分析模块与 processor/bundle。
2. 落地 SR overlay 渲染插件并注册。
3. 前端回放与 catalog/store 接入。
4. 测试与门禁（pytest + frontend build + doc_audit）。

## 任务拆解

- [x] 新增 `backend/app/factor/processor_sr.py`、`backend/app/factor/bundles/sr.py`
- [x] 新增 SR 算法模块 `backend/app/factor/sr_analyzer.py`、`backend/app/factor/sr_analyzer_support.py`、`backend/app/factor/sr_component.py`
- [x] 新增 `backend/app/overlay/renderer_sr.py` 并注册到 `renderer_plugins.py`
- [x] 前端接入 `frontend/src/services/factorCatalog.ts`、`frontend/src/state/factorStore.ts`、`frontend/src/widgets/chart/replayFactorSlices.ts`
- [x] 补测试：`backend/tests/test_sr_factor.py` + 现有默认组件/manifest/catalog/overlay 测试更新
- [x] skill 流程补充脚手架命令：`tc-planning`、`tc-e2e-gate`、`tc-verify`

## 风险与回滚

- 风险
  - SR 事件 payload 偏大（snapshot 全量）
  - 长窗口下 SR 线数量导致 overlay patch 增长
- 回滚
  - 一步回滚：`git revert <sr-commit>`
  - 或临时禁用：从 `backend/app/factor/bundles/sr.py` / `backend/app/overlay/renderer_sr.py` 移除注册（仅调试场景）

## 验收标准

- `pytest -q` 通过
- `cd frontend && npm run build` 通过
- `bash docs/scripts/doc_audit.sh` 通过
- 因子目录无兼容层/遗留双轨（`quality_gate` 可通过）

## E2E 用户故事（门禁）

### Story ID / E2E Test Case（必须）
- Story ID：`2026-02-13/sr-factor/sr-major-two-pivots-draw`
- 关联 Plan：`docs/plan/2026-02-13-sr-factor-major-only-v1.md`
- E2E 测试用例：
  - Test file path: `backend/tests/test_sr_factor.py`
  - Test name(s): `SrFactorTests::test_factor_and_overlay_pipeline_produces_sr_draw_instruction`
  - Runner: `pytest`

### Persona / Goal
- Persona：量化策略研发
- Goal：在同一闭环里看到 SR 因子产出并渲染到 overlay

### Entry / Exit（明确入口与出口）
- Entry：写入一段可产生 2 个 major resistance pivot 的闭合 K 线并触发 `factor_orchestrator.ingest_closed`
- Exit：
  - `factor_store` 中出现 `factor_name="sr"` 的 `sr.snapshot` 事件
  - `overlay_store` 中出现 `feature` 以 `sr.` 开头的绘图定义

### Concrete Scenario（必须：写“具体数值”，禁止空泛）
- Chart / Symbol:
  - series_id: `binance:futures:BTC/USDT:1m`
  - timezone: UTC
- Initial State：
  - DB empty: yes
  - 9 根 K 线（`base=1700100000`, step=60）
  - highs: `[10,11,15,11,10,11,15,11,10]`
  - lows: 全部 `5`
  - closes: `[9,10,14,10,9,10,14,10,9]`
- Trigger Event：
  - `up_to_candle_time = 1700100480`
  - 触发 `factor_orchestrator.ingest_closed` + `overlay_orchestrator.ingest_closed`
- Expected observable outcome：
  - SR 事件至少 1 条（`kind=sr.snapshot`）
  - overlay defs 中至少 1 条 `feature in {sr.active, sr.broken}`

### Preconditions（前置条件）
- 使用临时 sqlite（测试内创建）
- 无需启动 dev server

### Main Flow（主流程步骤 + 断言）
1) Step: 写入测试 K 线并执行 factor ingest
   - Assertions: `factor_store.get_events_between_times(..., factor_name="sr")` 非空
2) Step: 执行 overlay ingest
   - Assertions: `overlay_store.get_latest_defs_up_to_time(...)` 中存在 `payload.feature.startswith("sr.")`
3) Step: 校验 SR 线可回放
   - Assertions: `sr.snapshot` payload 包含 `levels` 字段（数组）

### Produced Data（产生的数据）
- `factor_events`
  - keys/fields: `factor_name`, `kind`, `event_key`, `payload`
- `overlay_instruction_defs`
  - keys/fields: `instruction_id`, `payload.feature`, `payload.points`

### Verification Commands（必须可复制运行）
- `pytest -q backend/tests/test_sr_factor.py`
  - Expected: 新增 3 条 SR 测试通过
- `pytest -q backend/tests/test_overlay_renderer_plugins.py`
  - Expected: SR renderer 相关断言通过

### Rollback（回滚）
- `git revert <sr-commit>`

## 变更记录
- 2026-02-13: 创建并进入开发中
