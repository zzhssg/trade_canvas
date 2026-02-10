---
title: Factor 完全插件化（Phase N：默认 bundle 声明进一步去重）
status: 待验收
owner: codex
created: 2026-02-10
updated: 2026-02-10
---

## 背景

Phase M 已把默认装配收敛到单点，但 bundle 结构仍保留冗余字段：
- `factor_name`
- `processor_builder`
- `slice_plugin_builder`

其中 `factor_name` 与 processor/slice plugin 的 `spec.factor_name` 语义重复，容易形成“声明名与实现名不一致”的维护成本。

## 目标 / 非目标

目标：
- 去掉 bundle 中冗余 `factor_name` 字段；
- 以 processor/slice plugin 的 `spec.factor_name` 为唯一真源；
- 保留 fail-fast 校验：默认配对中若 processor 与 slice plugin 名称不一致立即报错。

非目标：
- 不改因子算法，不改读写协议；
- 不改新增默认 factor 的入口文件（仍在 `factor_default_components.py` 单点追加）。

## 方案概述

1) `FactorDefaultBundleSpec` 精简为 `processor_builder + slice_plugin_builder`。
2) `build_factor_components_from_bundles()` 改为直接对比 `processor.spec.factor_name` 与 `slice_plugin.spec.factor_name`。
3) 更新回归测试与文档表述，保证接入说明与代码一致。

## 验收标准

- `pytest -q backend/tests/test_factor_default_components.py backend/tests/test_factor_manifest.py`
- `mypy --follow-imports=skip backend/app/factor_default_components.py`
- `pytest -q`
- `bash docs/scripts/doc_audit.sh`

## E2E 用户故事（门禁）

- Persona：因子平台维护者。
- 入口：在默认 bundle 中配置一组 processor + slice plugin。
- 主链路：manifest 消费默认组件并构建 topo 执行图。
- 出口断言：
  - 正常配对时写路径/读路径默认装配可用；
  - 错配时返回 `factor_default_bundle_mismatch:*` fail-fast。

## 回滚

- 单提交回滚：`git revert <sha>`
- 最小文件回退：
  - `/Users/rick/code/trade_canvas/backend/app/factor_default_components.py`
  - `/Users/rick/code/trade_canvas/backend/tests/test_factor_default_components.py`
  - `/Users/rick/code/trade_canvas/docs/core/factor-modular-architecture.md`
  - `/Users/rick/code/trade_canvas/docs/core/contracts/factor_sdk_v1.md`
