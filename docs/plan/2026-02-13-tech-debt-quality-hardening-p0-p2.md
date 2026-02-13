---
title: tech debt quality hardening p0 p2
status: 开发中
owner: codex
created: 2026-02-13
updated: 2026-02-13
---

## 背景

- 前端 `ChartView.tsx` 达到 2950 行，承担 K 线、overlay、replay、WS、draw tools 等多类职责，改动易引发连锁回归。
- 后端 `backend/app/` 目录平铺文件比例过高（166 个 py 中 134 个在顶层），新增逻辑易继续散落。
- `RuntimeFlags` 字段数量高（51 个），构建链路存在参数“散弹式修改”风险。
- `dependencies.py` 主要为 re-export，存在依赖注入接入路径冗长问题。

## 目标 / 非目标

- 目标：
  - 用“可回滚的小步”降低高耦合区域的改动风险。
  - 先做无行为改动的结构抽离，再做契约级重构。
  - 每一步都能用现有门禁验证（`pytest -q` / `cd frontend && npm run build` / `bash docs/scripts/doc_audit.sh`）。
- 非目标：
  - 不在一轮内完成后端全目录重命名或一次性大迁移。
  - 不在无回归保护的情况下改写 replay/market 主链路语义。

## 方案概述

- 方案 A（一次性重构）：
  - 同时拆 `ChartView`、重分后端目录、重构 flags/DI。
  - 优点：短期表面“干净”；缺点：回滚困难、风险高、E2E 漂移概率大。
- 方案 B（分层渐进，推荐）：
  - 先抽离无行为 hooks/模块，补回归测试，再推进 flags/目录治理。
  - 优点：每步可验收可回滚，符合主链路稳定性要求；缺点：周期更长。
- 采用：**方案 B**。

## 里程碑

- M0（已启动）：前端 God Component 无行为抽离（先拆 selector/hook 绑定层）。
- M1：`ChartView` 职责拆分到 `useChartCandles` / `useWsSync` / `useReplayController`（保持行为一致）。
- M2：后端 ingest 微碎片治理（先合并明显纯包装模块，保留可测边界）。
- M3：flags 分组（`RuntimeFlags` 领域化）+ builder/supervisor 传参收敛。
- M4：DI 简化（减少 re-export 仪式化层），并补边界测试。

## 任务拆解

- [x] P0-1 前端第一步：抽离 replay store 绑定层为独立 hook（无行为改动）
  - 改什么：新增 `frontend/src/widgets/chart/useReplayBindings.ts`，`ChartView.tsx` 改为调用 hook。
  - 怎么验收：`cd frontend && npx tsc -b --pretty false --noEmit`。
  - 怎么回滚：`git revert <commit>` 或回退两个文件到改动前版本。
- [x] P0-2 前端第二步：提取 `useWsSync`（WS 建连/解析/关闭与 catchup）
  - 改什么：从 `ChartView.tsx` 抽离 WS 生命周期与消息分发。
  - 怎么验收：`cd frontend && npm run build` + 目标 E2E。
  - 怎么回滚：仅回退新增 hook 与调用点。
- [x] P0-3 前端第三步：提取 `useReplayController`（prepare/build/window/playback）
  - 改什么：replay 状态推进、窗口拉取与 index 驱动统一到 hook。
  - 怎么验收：`cd frontend && npm run build` + replay 相关用例。
  - 怎么回滚：回退 replay hook 接入改动。
  - 进度（2026-02-13）：已完成分步 1（`useReplayController` 承接 reset/prepare/playback timer）+ 分步 2（`useReplayPackageWindowSync` 承接 package/window 拉取与应用链路），`ChartView` 保持编排职责。
- [ ] P1-1 后端 ingest 模块治理（碎片合并）
  - 改什么：评估并合并明显“dict 包装/纯转发”的 policy/registry 文件，保留必要边界。
  - 怎么验收：`pytest -q backend/tests/test_ingest_* backend/tests/test_market_data_services.py`。
  - 怎么回滚：按单次原子提交逐个 `git revert`。
- [ ] P1-2 flags 领域分组（ingest/factor/overlay/replay）
  - 改什么：先加分组 dataclass 兼容层，再迁移调用方，最后收敛扁平字段访问。
  - 怎么验收：`pytest -q backend/tests/test_runtime_flags.py backend/tests/test_backend_architecture_flags.py`。
  - 怎么回滚：保留旧字段兼容路径，开关控制切换。
- [ ] P2-1 DI 简化
  - 改什么：减少 `dependencies.py` 聚合出口，路由逐步改为直接依赖 `AppContainerDep` 或领域 deps。
  - 怎么验收：`pytest -q backend/tests/test_app_state_boundary.py`。
  - 怎么回滚：保留旧导出别名过渡一轮。

## 风险与回滚

- 风险 1：ChartView 拆分引入渲染时序差异。
  - 缓解：先抽“只读绑定层”，每步只做一个职责的搬迁。
- 风险 2：后端 flags/DI 改动导致初始化链路断裂。
  - 缓解：先加兼容层，不做一次性删旧字段。
- 风险 3：目录迁移导致 import 漂移。
  - 缓解：先局部子包化，配合边界测试与 `pytest -q --collect-only`。
- 回滚策略：
  - 每一步保持原子提交，失败后优先 `git revert`。
  - 高风险行为变更配套 `TRADE_CANVAS_ENABLE_*` kill-switch。

## 验收标准

- 前端：`cd frontend && npm run build` 通过，ChartView 行数持续下降且主链路行为不变。
- 后端：`pytest -q` 通过，关键边界测试（app_state_boundary / runtime_flags / ingest）不回退。
- 文档：`bash docs/scripts/doc_audit.sh` 通过，计划状态与变更记录同步。

## 变更记录

- 2026-02-13: 创建（草稿）
- 2026-02-13: 进入开发中；完成 P0-1（抽离 replay bindings hook，无行为改动）
- 2026-02-13: 完成 P0-2（抽离 useWsSync，统一 WS 建连/解析/分发，无行为改动）
- 2026-02-13: P0-3 分步 1 完成（新增 useReplayController，承接 replay reset/prepare/playback timer）
- 2026-02-13: P0-3 分步 2 完成（新增 useReplayPackageWindowSync，承接 replay package/window 同步与切片应用链路）
