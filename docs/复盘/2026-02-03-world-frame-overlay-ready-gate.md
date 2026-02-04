---
title: 复盘：world frame 点查未强制 overlay 就绪导致“对齐假象”
status: done
created: 2026-02-03
updated: 2026-02-03
---

# 复盘：world frame 点查未强制 overlay 就绪导致“对齐假象”

## 背景

我们新增了统一世界状态读口：
- `GET /api/frame/live`
- `GET /api/frame/at_time`

其内部组合投影：
- `factor_slices`（`/api/factor/slices`）
- `draw_state`（`/api/draw/delta?at_time=t`）

## 问题

在 `draw/delta` 的 `at_time` 点查语义下，如果 overlay head 未落盘（例如关闭 overlay ingest / 异常未推进），
仍可能返回 `to_candle_time=t` 但 `instruction_catalog_patch/active_ids` 为空，造成“看起来对齐了 t，但其实 overlay 没构建到位”的假象。

这会破坏我们最重要的不变量：对齐失败必须 fail-safe（`ledger_out_of_sync`），否则会出现“画对了但算错了 / 链路断了”类漂移风险。

## 影响

- replay/point query：前端以为拿到 `t` 的世界状态，但绘图侧实际缺证据（空 patch）
- 验收误判：对齐门禁无法在测试中暴露

## 根因

`draw/delta` 的点查分支只在 `overlay_head < aligned` 时报错，没有把 `overlay_head is None` 视为“未构建”。

## 如何避免（检查清单）

- [ ] 任何 `at_time` 点查输出都必须验证“真源已推进到位”（head pointer 存在且 >= aligned）
- [ ] 对齐门禁测试必须覆盖 “缺失 ledger/head 时拒绝输出”
- [ ] 组合投影接口（frame）不应让子组件的弱门禁漏出

## 关联与证据

- 修复点：`backend/app/main.py`（`/api/draw/delta` at_time 分支）
- 回归测试：`backend/tests/test_world_state_frame_api.py`
- 验证命令：
  - `pytest -q`

