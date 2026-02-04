---
title: 经验：点查（at_time）必须校验 head 就绪（否则拒绝输出）
status: done
created: 2026-02-03
updated: 2026-02-03
---

# 经验：点查（at_time）必须校验 head 就绪（否则拒绝输出）

## 场景与目标

当系统提供 `at_time` 定点输出（replay/frame、draw/delta 点查、factor slice 点查）时，最容易出现一种“对齐假象”：
- 输出声称对齐到 `t`（`to_candle_time=t`、`candle_id=t`）
- 但底层 ledger/store 实际并未推进到 `t`（head pointer 缺失或落后）

目标：让定点输出在真源未就绪时 **必定 fail-safe**，避免前端/策略消费“空但对齐”的假数据。

## 可复用规则

- 对所有点查输出（含组合投影）统一门禁：
  - `head_time is None` 或 `head_time < aligned_time` → 返回 `ledger_out_of_sync`（或 `build_required`）
- 组合投影（frame/world state）必须以最弱环节为准：
  - 任意子模块未就绪就拒绝整帧输出（避免不同子系统对齐点分裂）

## 为什么有效

- 把“缺失产物”显式化为错误，而不是隐式返回空数组，能让测试与 E2E 在正确位置失败。
- 让 live/replay 共用一套契约时，避免“live 可用、replay 漂移”的隐藏分叉。

## 关联与证据

- 关键代码：`backend/app/main.py`（`/api/draw/delta` 点查门禁）
- 回归测试：`backend/tests/test_world_state_frame_api.py`
- 验证命令：
  - `pytest -q`

