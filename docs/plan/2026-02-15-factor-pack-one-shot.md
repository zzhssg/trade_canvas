---
title: Factor 一次性插件化收敛（Pack + 全链路自动装配）
status: 待验收
owner: codex
created: 2026-02-15
updated: 2026-02-15
---

## 背景

当前仓库已完成因子 processor/slice/overlay/signal 的基础插件化，但“新增因子”仍需触达多处主流程：
- factor 写链路状态结构是固定字段；
- overlay 默认插件仍是静态列表；
- scaffold 只生成 processor + bundle，无法覆盖实盘/绘图接入点。

这导致新增一个因子时，改动面仍偏大，且存在漏接风险。

## 目标 / 非目标

目标：
- 把新增因子接入点收敛为“因子包声明 +（可选）脚手架选项”，避免改 orchestrator 主流程；
- 保持 factor -> overlay -> world/replay -> freqtrade/backtest 的现有契约不变；
- 保证回滚路径是原子 commit + git revert。

非目标：
- 不改已有因子算法语义（pivot/pen/zhongshu/anchor/sr）；
- 不新增 HTTP/WS 协议字段；
- 不引入 forming 进入因子引擎。

## 约束 / 边界（必填）

- 业务/技术约束：closed candle 是唯一权威输入；读路径禁止隐式重算。
- 不可变契约（Schema/API/字段口径）：`/api/factor/slices`、`/api/draw/delta`、`/api/world/*`、freqtrade `tc_*` 列口径保持不变。
- 目录边界（涉及目录 + 是否跨边界）：涉及 `backend/app/factor`、`backend/app/overlay`、`backend/app/freqtrade`、`scripts`、`tests`、`docs`（跨边界，集成回合）。
- 开关/灰度策略（`VITE_ENABLE_*` / `TRADE_CANVAS_ENABLE_*`）：不新增开关，沿用现有 runtime flags。

## 成功指标（可量化，必填）

- 指标 1：新增因子主链路接入时，不需要改 `factor/orchestrator_ingest.py`、`factor/tick_executor.py`、`overlay/orchestrator.py`。
- 指标 2：新增 overlay renderer 时，不需要改 `overlay/renderer_plugins.py` 静态列表。
- 证据命令与产物路径：
  - `pytest -q backend/tests/test_factor_tick_executor.py backend/tests/test_factor_orchestrator_settings.py backend/tests/test_overlay_renderer_plugins.py backend/tests/test_freqtrade_adapter_v1.py tests/test_factor_scaffold_cli.py`
  - `pytest -q`
  - `bash docs/scripts/doc_audit.sh`

## YAGNI / 本轮明确不做（必填）

- 本轮不做：重写全部既有因子到新状态协议；delta ledger 全量重构。
- 不做原因：风险过高，且与“新增因子改动最小化”目标无直接必要关系。
- 重新评估触发条件：当新增第一个使用新状态协议的因子时，再评估是否迁移既有因子。

## 方案概述

1) Factor 引擎状态扩展：引入命名空间 `plugin_states`，新增因子可自带状态而不触碰固定字段。
2) Runtime 能力扩展：`FactorRuntimeContext` 改为服务字典，保留 `anchor_processor` 兼容访问器。
3) Overlay 插件自动发现：`renderer_*.py` 自发现 + topo 排序，删除静态默认列表耦合。
4) Scaffold 覆盖全链路：新增可选模板生成 overlay renderer / freqtrade signal 插件。
5) 回归测试与文档同步，保证 DoD 与可回滚。

## 里程碑

- M1：factor 引擎状态协议扩展 + 兼容。
- M2：overlay renderer 自动发现。
- M3：scaffold 扩展 + 回归。
- M4：文档与验收证据。

## 任务拆解
- [x] M1：扩展 `plugin_states` 与 runtime service registry，保持现有因子行为不变。
- [x] M2：overlay 渲染插件改为动态发现，保持 topo 顺序与输出一致。
- [x] M3：`new_factor_scaffold.py` 支持可选生成 overlay/signal 插件模板。
- [x] M4：补齐测试、文档、门禁证据。

## 风险与回滚

- 风险：状态协议扩展可能影响 tick 执行与 bootstrap 恢复。
- 缓解：先保留旧字段访问器，新增字段默认空值；先跑核心单测再全量。
- 回滚：按里程碑原子提交，必要时 `git revert <sha>` 单步回退。

## 验收标准

- `pytest -q backend/tests/test_factor_tick_executor.py backend/tests/test_factor_orchestrator_settings.py backend/tests/test_overlay_renderer_plugins.py backend/tests/test_freqtrade_adapter_v1.py tests/test_factor_scaffold_cli.py`
- `pytest -q`
- `bash docs/scripts/doc_audit.sh`

## E2E 用户故事（门禁）

- Story ID：`2026-02-15/factor-pack/minimal-change-factor-onboarding`
- Persona：因子平台开发者。
- Goal：新增一个因子时，最小改动完成因子产生、绘图、freqtrade 信号接入，不改主流程 orchestrator。
- 主流程断言：
  1) 新因子通过 scaffold 生成骨架并实现最小 run_tick；
  2) ingest 后可在 factor slices 中读到该因子；
  3) overlay/freqtrade 可通过插件声明接入而非主流程改动。
- 证据：上述测试命令 + 关键输出。

## 变更记录
- 2026-02-15：创建并进入开发中。
- 2026-02-15：完成 M1~M4，实现状态命名空间、overlay 自动发现、scaffold 全链路模板与回归证据。
