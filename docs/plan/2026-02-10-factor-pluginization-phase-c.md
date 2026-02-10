---
title: Factor 完全插件化（Phase C：读路径 Slice 插件化）
status: done
owner: codex
created: 2026-02-10
updated: 2026-02-10
---

## 目标

- 把 `FactorSlicesService` 中按因子硬编码的快照组装逻辑下沉为插件。
- 让读路径与写路径都通过 `factor_name/depends_on` 拓扑调度，减少新增 factor 的散点改动。
- 保持 `/api/factor/slices`、`/api/draw/delta`、world frame 等上游消费者行为不变。

## 变更范围

- 新增读路径插件契约与默认插件：
  - `/Users/rick/code/trade_canvas/backend/app/factor_slice_plugin_contract.py`
  - `/Users/rick/code/trade_canvas/backend/app/factor_slice_plugins.py`
- 重构读路径调度：
  - `/Users/rick/code/trade_canvas/backend/app/factor_slices_service.py`
  - 改为插件注册 + FactorGraph topo 调度，不再手写按因子分支。
- 新增回归测试：
  - `/Users/rick/code/trade_canvas/backend/tests/test_factor_slice_plugins.py`
  - 覆盖默认插件图、服务调度顺序、bucket 冲突防护。
- 文档同步：
  - `/Users/rick/code/trade_canvas/docs/core/contracts/factor_plugin_v1.md`
  - `/Users/rick/code/trade_canvas/docs/core/contracts/factor_graph_v1.md`
  - `/Users/rick/code/trade_canvas/docs/core/contracts/factor_sdk_v1.md`
  - `/Users/rick/code/trade_canvas/docs/core/factor-modular-architecture.md`

## 验收

- `pytest -q backend/tests/test_factor_slice_plugins.py backend/tests/test_factor_slices_api.py backend/tests/test_draw_delta_api.py`（17 passed）
- `pytest -q`（181 passed）
- `bash docs/scripts/doc_audit.sh`（pass）

## 回滚

- 单提交回滚：`git revert <sha>`
- 最小文件回退：
  - `/Users/rick/code/trade_canvas/backend/app/factor_slice_plugin_contract.py`
  - `/Users/rick/code/trade_canvas/backend/app/factor_slice_plugins.py`
  - `/Users/rick/code/trade_canvas/backend/app/factor_slices_service.py`
  - `/Users/rick/code/trade_canvas/backend/tests/test_factor_slice_plugins.py`
