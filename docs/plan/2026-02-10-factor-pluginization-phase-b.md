---
title: Factor 完全插件化（Phase B：Graph 驱动 Tick 调度）
status: done
owner: codex
created: 2026-02-10
updated: 2026-02-10
---

## 目标

- 把 orchestrator 的单 tick 处理从大段内联流程拆成 factor step handlers。
- 在执行层强制走 `FactorGraph.topo_order`，减少未来新增 factor 时的手工串联风险。
- 保持事件语义与对外契约不变（history/head 输出不变）。

## 变更范围

- 调度重构：
  - `/Users/rick/code/trade_canvas/backend/app/factor_orchestrator.py`
  - 新增 `_FactorTickState`，并拆分 `_run_pivot_step` / `_run_pen_step` / `_run_zhongshu_step` / `_run_anchor_step`。
  - 新增 `_run_tick_steps(...)` 统一按 graph topo 顺序执行。
- 回归测试：
  - `/Users/rick/code/trade_canvas/backend/tests/test_factor_orchestrator_settings.py`
  - 新增“tick step 按 topo_order 调度”测试。
- 文档同步：
  - `/Users/rick/code/trade_canvas/docs/core/factor-modular-architecture.md`

## 验收

- `pytest -q backend/tests/test_factor_orchestrator_settings.py backend/tests/test_factor_registry.py backend/tests/test_factor_graph.py`（pass）
- `pytest -q`（pass）
- `bash docs/scripts/doc_audit.sh`（pass）

## 回滚

- 单提交回滚：`git revert <sha>`
- 最小文件回退：
  - `/Users/rick/code/trade_canvas/backend/app/factor_orchestrator.py`
  - `/Users/rick/code/trade_canvas/backend/tests/test_factor_orchestrator_settings.py`
