---
title: Factor 完全插件化（Phase E：写路径 Tick Hook 插件化）
status: done
owner: codex
created: 2026-02-10
updated: 2026-02-10
---

## 目标

- 把写路径 tick 执行从 orchestrator 内的固定因子分支切到插件 `run_tick(...)` 调度。
- 让写路径与 manifest 注册结果一致，减少新增 factor 时对 orchestrator 的改动面。
- 保持现有行为不变（事件语义、head 语义、对外接口不变）。

## 变更范围

- 写路径调度插件化：
  - `/Users/rick/code/trade_canvas/backend/app/factor_orchestrator.py`
  - 删除固定 `_run_pivot_step/_run_pen_step/_run_zhongshu_step/_run_anchor_step` 分支；
  - 改为按 `FactorGraph.topo_order` 调用注册插件 `run_tick(...)`；
  - 缺失 hook 时 fail-fast（`factor_missing_run_tick:<factor>`）。
- processor 补齐 tick hook：
  - `/Users/rick/code/trade_canvas/backend/app/factor_processor_pivot.py`
  - `/Users/rick/code/trade_canvas/backend/app/factor_processor_pen.py`
  - `/Users/rick/code/trade_canvas/backend/app/factor_processor_zhongshu.py`
  - `/Users/rick/code/trade_canvas/backend/app/factor_processor_anchor.py`
- 插件契约与兼容别名：
  - `/Users/rick/code/trade_canvas/backend/app/factor_plugin_contract.py`（新增 `FactorTickPlugin`）
  - `/Users/rick/code/trade_canvas/backend/app/factor_registry.py`（`FactorProcessor` 对齐到 tick plugin）
- 指纹覆盖增强：
  - `/Users/rick/code/trade_canvas/backend/app/factor_orchestrator.py`
  - 指纹新增插件实现文件哈希（按注册插件动态收集），避免插件代码变更漏重算。
- 回归测试：
  - `/Users/rick/code/trade_canvas/backend/tests/test_factor_orchestrator_settings.py`
  - 新增“插件缺失 run_tick 时 fail-fast”测试，并更新 topo 调度测试。
- 文档同步：
  - `/Users/rick/code/trade_canvas/docs/core/contracts/factor_plugin_v1.md`
  - `/Users/rick/code/trade_canvas/docs/core/factor-modular-architecture.md`

## 验收

- `pytest -q backend/tests/test_factor_orchestrator_settings.py backend/tests/test_factor_registry.py backend/tests/test_factor_plugin_registry.py backend/tests/test_factor_manifest.py`（26 passed）
- `pytest -q`（189 passed）
- `bash docs/scripts/doc_audit.sh`（pass）

## 回滚

- 单提交回滚：`git revert <sha>`
- 最小文件回退：
  - `/Users/rick/code/trade_canvas/backend/app/factor_orchestrator.py`
  - `/Users/rick/code/trade_canvas/backend/app/factor_processor_pivot.py`
  - `/Users/rick/code/trade_canvas/backend/app/factor_processor_pen.py`
  - `/Users/rick/code/trade_canvas/backend/app/factor_processor_zhongshu.py`
  - `/Users/rick/code/trade_canvas/backend/app/factor_processor_anchor.py`
  - `/Users/rick/code/trade_canvas/backend/app/factor_plugin_contract.py`
  - `/Users/rick/code/trade_canvas/backend/app/factor_registry.py`
  - `/Users/rick/code/trade_canvas/backend/tests/test_factor_orchestrator_settings.py`
