---
title: 经验：用兼容投影 + feature flag 小步收敛绘图读口
status: done
created: 2026-02-02
updated: 2026-02-02
---

# 经验：用兼容投影 + feature flag 小步收敛绘图读口

## 场景与目标

当系统里同时存在多种“绘图增量形态”（例如 overlay catalog patch、plot events/lines）时，直接替换很容易引入漂移与不可回滚风险。

目标是：
- 前端只实现一次 apply 引擎（统一消费形状）
- 后端先提供一个兼容投影读口，逐步把真源切到 delta ledger
- 全程可回滚

## 做对了什么（可复用动作）

1) **先统一“读口形状”，不动生产者**
- 新增 `GET /api/draw/delta` 作为兼容投影，先复用 `overlay/delta` 的指令输出（`instruction_catalog_patch/active_ids`）。
- `series_points` 先返回空 `{}`，避免为了“统一”而引入旁路重算。

2) **前端用 feature flag 切流**
- 默认仍走老接口；通过 `VITE_ENABLE_DRAW_DELTA=1` 切到新接口。
- 回滚成本极低（改 env 即可），适合联调期快速定位问题。

3) **写“等价性回归”而不是只写冒烟**
- 后端测试直接断言 `/api/draw/delta` 与 `/api/overlay/delta` 的关键字段一致（patch、active_ids、cursor），避免“新接口悄悄变味”。

## 为什么有效（机制/约束）

- 兼容投影把风险隔离在“读口层”，不会破坏生产者与存储语义。
- feature flag 让切换变成可控实验，不需要一次性迁移。
- 等价性回归确保“统一读口”不会因为重构而悄悄漂移。

## 复用方式（下次如何触发）

当你要把多条下游消费口径收敛到一个契约时：

- [ ] 先落一个“统一 shape”的兼容投影端点（只读、无重算）
- [ ] 前端/消费者加 feature flag 切流
- [ ] 写 1 条等价性回归（新旧输出一致）
- [ ] 等主链路真源（ledger/delta）准备好后，再替换投影的数据来源

## 关联与证据

- 关键文件：
  - `docs/core/contracts/draw_delta_v1.md`
  - `backend/tests/test_draw_delta_api.py`
  - `frontend/src/widgets/ChartView.tsx`
- 验证命令：
  - `pytest -q`
  - `cd frontend && npm run build`

