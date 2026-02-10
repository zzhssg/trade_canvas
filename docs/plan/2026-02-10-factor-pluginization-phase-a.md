---
title: Factor 完全插件化（Phase A：插件契约与注册中心）
status: done
owner: codex
created: 2026-02-10
updated: 2026-02-10
---

## 目标

- 建立后端因子插件最小契约，统一 `factor_name/depends_on` 声明。
- 抽离通用插件注册中心，替代历史 `FactorRegistry` 内联实现。
- 保持现有 processor 路径兼容，做到“行为不变先收口”。

## 变更范围

- 新增：
  - `/Users/rick/code/trade_canvas/backend/app/factor_plugin_contract.py`
  - `/Users/rick/code/trade_canvas/backend/app/factor_plugin_registry.py`
  - `/Users/rick/code/trade_canvas/backend/tests/test_factor_plugin_registry.py`
  - `/Users/rick/code/trade_canvas/docs/core/contracts/factor_plugin_v1.md`
- 兼容改造：
  - `/Users/rick/code/trade_canvas/backend/app/factor_registry.py`
- 文档同步：
  - `/Users/rick/code/trade_canvas/docs/core/contracts/factor_graph_v1.md`
  - `/Users/rick/code/trade_canvas/docs/core/contracts/factor_sdk_v1.md`
  - `/Users/rick/code/trade_canvas/docs/core/factor-modular-architecture.md`

## 验收

- `pytest -q backend/tests/test_factor_plugin_registry.py backend/tests/test_factor_registry.py backend/tests/test_factor_graph.py`（18 passed）
- `pytest -q`（176 passed）
- `bash docs/scripts/doc_audit.sh`（pass）

## 回滚

- 单提交回滚：`git revert <sha>`
- 最小文件回退：
  - `/Users/rick/code/trade_canvas/backend/app/factor_plugin_contract.py`
  - `/Users/rick/code/trade_canvas/backend/app/factor_plugin_registry.py`
  - `/Users/rick/code/trade_canvas/backend/app/factor_registry.py`
  - `/Users/rick/code/trade_canvas/docs/core/contracts/factor_plugin_v1.md`
