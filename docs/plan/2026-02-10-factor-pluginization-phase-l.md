---
title: Factor 完全插件化（Phase L：Slice bucket 声明去重并内聚）
status: 待验收
owner: codex
created: 2026-02-10
updated: 2026-02-10
---

## 背景

当前 slice bucket 映射存在“声明位置分离”问题：
- `factor_slice_plugins.py` 通过 `build_default_slice_bucket_specs()` 间接读取 bucket；
- 新增 factor 时需要同步改 `factor_processor_slice_buckets.py`，存在接入点分散与漏改风险。

## 目标 / 非目标

目标：
- 把 bucket 映射声明内聚到各 `XxxSlicePlugin.bucket_specs`，实现“插件自描述”；
- `build_default_slice_bucket_specs()` 退化为兼容聚合入口（从默认 slice 插件导出），减少重复维护；
- 保持默认 bucket 行为与现有读路径输出完全一致。

非目标：
- 不修改 `/api/factor/slices` 协议字段；
- 不调整因子算法逻辑（pivot/pen/zhongshu/anchor）。

## 方案概述

1) 在 `factor_slice_plugins.py` 内为 pivot/pen/zhongshu/anchor 直接声明 `bucket_specs` 常量。
2) `factor_processor_slice_buckets.py` 的 `build_default_slice_bucket_specs()` 改为从 `build_default_factor_slice_plugins()` 聚合导出，作为兼容层保留。
3) 同步文档：
   - 更新模块化架构文档中“新增 factor 固定接入面”；
   - 更新 SDK 契约中的 slice bucket 接入说明。

## 验收标准

- `pytest -q backend/tests/test_factor_slice_plugins.py backend/tests/test_factor_registry.py`
- `pytest -q`
- `bash docs/scripts/doc_audit.sh`

## E2E 用户故事（门禁）

- Persona：因子插件维护者。
- 入口：新增一个 `XxxSlicePlugin` 并在插件内声明 `bucket_specs`。
- 主链路：服务启动后 `FactorSlicesService` 能按 bucket 正常归类事件并产出快照。
- 出口断言：
  - 默认 bucket 集合与默认插件声明一致；
  - 不需要额外改独立 bucket 配置文件。

## 回滚

- 单提交回滚：`git revert <sha>`
- 最小文件回退：
  - `/Users/rick/code/trade_canvas/backend/app/factor_slice_plugins.py`
  - `/Users/rick/code/trade_canvas/backend/app/factor_processor_slice_buckets.py`
  - `/Users/rick/code/trade_canvas/docs/core/factor-modular-architecture.md`
  - `/Users/rick/code/trade_canvas/docs/core/contracts/factor_sdk_v1.md`
