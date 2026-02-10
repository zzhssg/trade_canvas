---
title: Factor 完全插件化（Phase D：统一 Manifest 装配）
status: done
owner: codex
created: 2026-02-10
updated: 2026-02-10
---

## 目标

- 把写路径 processor 装配与读路径 slice plugin 装配统一到同一份 manifest。
- 默认运行时不再依赖两份独立默认列表，避免“新增 factor 漏接一侧”。
- 保持对外行为不变（factor slices / draw delta / world frame 无协议变更）。

## 变更范围

- 新增统一装配清单：
  - `/Users/rick/code/trade_canvas/backend/app/factor_manifest.py`
  - 提供 `build_default_factor_manifest()` 与一致性校验（factor set + depends_on）。
- 接入默认运行时：
  - `/Users/rick/code/trade_canvas/backend/app/factor_orchestrator.py`
  - `/Users/rick/code/trade_canvas/backend/app/factor_slices_service.py`
  - 两条主链路默认都从 manifest 取装配。
- 新增回归测试：
  - `/Users/rick/code/trade_canvas/backend/tests/test_factor_manifest.py`
- 文档同步：
  - `/Users/rick/code/trade_canvas/docs/core/contracts/factor_plugin_v1.md`
  - `/Users/rick/code/trade_canvas/docs/core/contracts/factor_graph_v1.md`
  - `/Users/rick/code/trade_canvas/docs/core/contracts/factor_sdk_v1.md`
  - `/Users/rick/code/trade_canvas/docs/core/factor-modular-architecture.md`

## 验收

- `pytest -q --collect-only`（181 tests collected）
- `pytest -q backend/tests/test_factor_manifest.py backend/tests/test_factor_slice_plugins.py backend/tests/test_factor_registry.py backend/tests/test_factor_orchestrator_settings.py`（pass）
- `pytest -q`（pass）
- `mypy --follow-imports=skip backend/app/factor_manifest.py backend/app/factor_orchestrator.py backend/app/factor_slices_service.py backend/tests/test_factor_manifest.py`（pass）
- `bash docs/scripts/doc_audit.sh`（pass）

## 回滚

- 单提交回滚：`git revert <sha>`
- 最小文件回退：
  - `/Users/rick/code/trade_canvas/backend/app/factor_manifest.py`
  - `/Users/rick/code/trade_canvas/backend/app/factor_orchestrator.py`
  - `/Users/rick/code/trade_canvas/backend/app/factor_slices_service.py`
  - `/Users/rick/code/trade_canvas/backend/tests/test_factor_manifest.py`
