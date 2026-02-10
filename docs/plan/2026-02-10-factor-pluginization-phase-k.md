---
title: Factor 完全插件化（Phase K：读路径 freshness 门禁单一真源）
status: 待验收
owner: codex
created: 2026-02-10
updated: 2026-02-10
---

## 背景

`factor_read_freshness.py` 与 `read_models/factor_read_service.py` 都维护了 strict/non-strict 的 freshness 门禁，存在双实现漂移风险。

## 目标 / 非目标

目标：
- 将 strict/non-strict freshness 判定收敛到 `factor_read_freshness.py` 单一真源。
- `FactorReadService` 只做参数编排与调用，移除重复实现。
- 保持 strict mode 行为（`ledger_out_of_sync:factor`）与现有 API 返回语义不变。

非目标：
- 不改 `factor_slices` 响应结构，不改路由协议。

## 方案概述

1) `read_factor_slices_with_freshness(...)` 增加 `strict_mode`、`factor_store` 参数，支持显式策略与 head 读取来源注入。
2) `FactorReadService.read_slices(...)` 直接委托 `read_factor_slices_with_freshness(...)`，删除重复 strict 逻辑。
3) 增补测试：  
   - `test_factor_read_freshness.py` 覆盖 strict mode 拒绝与显式参数覆盖环境变量；
   - 回归 `test_factor_read_service.py` 与 `test_backend_architecture_flags.py`。

## 验收标准

- `pytest -q backend/tests/test_factor_read_freshness.py backend/tests/test_factor_read_service.py backend/tests/test_backend_architecture_flags.py`
- `mypy --follow-imports=skip backend/app/factor_read_freshness.py backend/app/read_models/factor_read_service.py`
- `pytest -q`

## E2E 用户故事（门禁）

- Persona：读路径主链路维护者。
- 入口：请求 `/api/factor/slices`，同时切换 `TRADE_CANVAS_ENABLE_READ_STRICT_MODE` 开关。
- 主链路：
  - strict=0：允许 read 触发按需 freshness ingest；
  - strict=1：当 factor head 落后于 aligned_time 时拒绝读取（409）。
- 出口断言：
  - strict 模式返回 `ledger_out_of_sync:factor`；
  - 非 strict 模式仍可走自动 freshness。

## 回滚

- 单提交回滚：`git revert <sha>`
- 最小文件回退：
  - `/Users/rick/code/trade_canvas/backend/app/factor_read_freshness.py`
  - `/Users/rick/code/trade_canvas/backend/app/read_models/factor_read_service.py`
  - `/Users/rick/code/trade_canvas/backend/tests/test_factor_read_freshness.py`
