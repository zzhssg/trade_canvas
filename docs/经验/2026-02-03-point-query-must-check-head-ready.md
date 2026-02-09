---
title: "点查必须校验 head 就绪（防止对齐假象）"
status: done
created: 2026-02-03
updated: 2026-02-09
---

# 点查必须校验 head 就绪（防止对齐假象）

## 问题背景

新增统一世界状态读口（`GET /api/frame/live`、`GET /api/frame/at_time`），内部组合投影 `factor_slices` 和 `draw_state`。在 `draw/delta` 的 `at_time` 点查语义下，如果 overlay head 未落盘（关闭 overlay ingest / 异常未推进），仍可能返回 `to_candle_time=t` 但 `instruction_catalog_patch/active_ids` 为空，造成"看起来对齐了 t，但其实 overlay 没构建到位"的假象。

具体问题：`draw/delta` 的点查分支只在 `overlay_head < aligned` 时报错，没有把 `overlay_head is None` 视为"未构建"。这会破坏最重要的不变量：对齐失败必须 fail-safe（`ledger_out_of_sync`）。

## 根因

`draw/delta` 的点查分支只在 `overlay_head < aligned` 时报错，没有把 `overlay_head is None` 视为"未构建"，导致缺失产物被隐式返回为空数组而非错误。

## 解法

- 对所有点查输出（含组合投影）统一门禁：`head_time is None` 或 `head_time < aligned_time` -> 返回 `ledger_out_of_sync`（或 `build_required`）。
- 组合投影（frame/world state）必须以最弱环节为准：任意子模块未就绪就拒绝整帧输出。
- 把"缺失产物"显式化为错误，而不是隐式返回空数组。

## 为什么有效

- 把"缺失产物"显式化为错误，能让测试与 E2E 在正确位置失败。
- 让 live/replay 共用一套契约时，避免"live 可用、replay 漂移"的隐藏分叉。

## 检查清单

**开发前**
- [ ] 先区分"数据缺失"与"数据过期"两类故障路径。

**开发中**
- [ ] 任何 `at_time` 点查输出都必须验证"真源已推进到位"（head pointer 存在且 >= aligned）。
- [ ] 组合投影接口（frame）不应让子组件的弱门禁漏出。

**验收时**
- [ ] 对齐门禁测试必须覆盖"缺失 ledger/head 时拒绝输出"。
- [ ] `pytest -q` 必过。

## 关联

- `backend/app/main.py`（`/api/draw/delta` at_time 分支）
- `backend/tests/test_world_state_frame_api.py`
- 验证命令：`pytest -q`
