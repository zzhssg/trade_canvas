---
title: "draw delta 兼容投影 + feature flag 小步收敛（避免契约漂移）"
status: done
created: 2026-02-02
updated: 2026-02-09
---

# draw delta 兼容投影 + feature flag 小步收敛（避免契约漂移）

## 问题背景

落地"统一绘图指令底座"第一步时，新增了契约 `draw_delta_v1.md`、兼容投影读口 `GET /api/draw/delta`、前端 feature flag `VITE_ENABLE_DRAW_DELTA=1` 切流。

具体漂移风险：`draw_delta_v1` 契约定义了 "fail-safe：candle_id 不一致必须拒绝输出（ledger_out_of_sync）"，但 v0 兼容投影的 `/api/draw/delta` 只是复用 `overlay_store` 的指令输出，并没有真正绑定"因子真源 ledger / candle_id 对齐"的门禁。结果是文档看起来像"已经具备强门禁"，但实现仍处于过渡态（best-effort），下游若误以为已具备 fail-safe，可能在切换时踩到"画对了但算错了"的风险。

## 根因

1. "终局契约"与"过渡实现"混在一个层次表达，没有显式写清实现状态与未实现门禁。
2. v0 数据源（overlay_store）并不天然具备 ledger 对齐语义，却被复用为统一读口。

## 解法

1. **先统一"读口形状"，不动生产者**：新增 `GET /api/draw/delta` 作为兼容投影，先复用 `overlay/delta` 的指令输出（`instruction_catalog_patch/active_ids`）；`series_points` 先返回空 `{}`，避免引入旁路重算。
2. **前端用 feature flag 切流**：默认仍走老接口；通过 `VITE_ENABLE_DRAW_DELTA=1` 切到新接口。回滚成本极低（改 env 即可）。
3. **写"等价性回归"而不是只写冒烟**：后端测试直接断言 `/api/draw/delta` 的关键字段幂等且可回归（patch、active_ids、cursor、at_time fail-safe）。

## 为什么有效

- 兼容投影把风险隔离在"读口层"，不会破坏生产者与存储语义。
- feature flag 让切换变成可控实验，不需要一次性迁移。
- 等价性回归确保"统一读口"不会因为重构而悄悄漂移。

## 检查清单

**开发前**
- [ ] 新增契约时，明确标注：目标形态 vs 当前实现状态（v0/v1）以及未实现项列表。
- [ ] 若引入 "MUST/硬门禁"，同步落一个最小可失败的测试（即使暂时 skip，也要写清触发条件）。

**开发中**
- [ ] 兼容投影端点必须在 doc 中标注为 "projection/compat"，避免下游把它当真源。
- [ ] 先落一个"统一 shape"的兼容投影端点（只读、无重算）。
- [ ] 前端/消费者加 feature flag 切流。
- [ ] 写 1 条等价性回归（新旧输出一致）。

**验收时**
- [ ] `bash docs/scripts/doc_audit.sh`，确保文档状态一致。
- [ ] `pytest -q`、`cd frontend && npm run build`。
- [ ] 若契约包含 fail-safe，至少有 1 条测试能失败在正确位置（例如返回 `ledger_out_of_sync`）。

## 关联

- `docs/core/contracts/draw_delta_v1.md`
- `backend/app/main.py`
- `backend/tests/test_draw_delta_api.py`
- `frontend/src/widgets/ChartView.tsx`
