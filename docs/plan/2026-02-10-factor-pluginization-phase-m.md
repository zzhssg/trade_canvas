---
title: Factor 完全插件化（Phase M：默认装配单点收敛）
status: 待验收
owner: codex
created: 2026-02-10
updated: 2026-02-10
---

## 背景

尽管 Phase L 已完成 slice bucket 去重，但默认因子装配仍有“双入口”风险：
- `build_default_factor_processors()`
- `build_default_factor_slice_plugins()`

新增默认 factor 时，需在两处分别维护顺序与对应关系，存在漏改/错配风险。

## 目标 / 非目标

目标：
- 引入单一默认装配源，统一声明 `factor_name + processor + slice_plugin` 配对；
- 让 `factor_manifest` 与兼容入口都从该单点生成默认组件；
- 增加 fail-fast 校验，发现默认装配中名称错配时立即报错。

非目标：
- 不修改因子算法逻辑；
- 不修改 `/api/factor/slices` 与写链路事件协议。

## 方案概述

1) 新增 `factor_default_components.py`：
   - 定义 `FactorDefaultBundleSpec`；
   - 统一维护默认 bundle 列表；
   - 提供 `build_default_factor_components()`。
2) `factor_manifest.py` 改为直接消费 `build_default_factor_components()`，避免双入口漂移。
3) `factor_processors.py` / `factor_slice_plugins.py` 的默认构建函数改为兼容包装（同样委托单点装配）。
4) 新增 `test_factor_default_components.py`，覆盖默认顺序与 mismatch fail-fast。
5) 同步 core 文档与 SDK/插件契约文档。

## 验收标准

- `pytest -q backend/tests/test_factor_default_components.py backend/tests/test_factor_manifest.py backend/tests/test_factor_slice_plugins.py backend/tests/test_factor_registry.py`
- `pytest -q`
- `bash docs/scripts/doc_audit.sh`

## E2E 用户故事（门禁）

- Persona：因子平台维护者。
- 入口：新增一个默认 factor（processor + slice plugin）。
- 主链路：只在默认 bundle 单点注册后，写路径与读路径都被 manifest 自动接入。
- 出口断言：
  - 默认 processors/slice_plugins 顺序一致；
  - 若 bundle 名称与 plugin spec 不一致，启动前即 fail-fast。

## 回滚

- 单提交回滚：`git revert <sha>`
- 最小文件回退：
  - `/Users/rick/code/trade_canvas/backend/app/factor_default_components.py`
  - `/Users/rick/code/trade_canvas/backend/app/factor_manifest.py`
  - `/Users/rick/code/trade_canvas/backend/app/factor_processors.py`
  - `/Users/rick/code/trade_canvas/backend/app/factor_slice_plugins.py`
  - `/Users/rick/code/trade_canvas/backend/tests/test_factor_default_components.py`
