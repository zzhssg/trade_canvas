---
title: 复盘：draw delta 契约与实现漂移风险
status: done
created: 2026-02-02
updated: 2026-02-02
---

# 复盘：draw delta 契约与实现漂移风险

## 背景

本次工作落地了“统一绘图指令底座”的第一小步：

- 新契约：`docs/core/contracts/draw_delta_v1.md`
- 新读口：`GET /api/draw/delta`（兼容投影）
- 前端 feature flag：`VITE_ENABLE_DRAW_DELTA=1` 切流

相关代码：
- `backend/app/main.py`
- `backend/app/schemas.py`
- `frontend/src/widgets/ChartView.tsx`

## 具体问题（可复现的漂移点）

`draw_delta_v1` 契约中定义了 “fail-safe：candle_id 不一致必须拒绝输出（ledger_out_of_sync）”，但当前 v0 兼容投影的 `/api/draw/delta` 只是复用 `overlay_store` 的指令输出，并没有真正绑定 “因子真源 ledger / candle_id 对齐” 的门禁。

结果是：
- 文档看起来像“已经具备强门禁”，但实现仍处于过渡态（best-effort）。
- 下游若误以为已具备 fail-safe，可能在未来某次切换时踩到“画对了但算错了 / 链路未对齐”的风险。

## 影响与代价

- 影响：契约与实现的认知不一致，容易导致错误的集成假设（尤其在接入策略/实盘时）。
- 代价：后续需要补门禁时，可能要同时改后端返回错误码、前端处理逻辑、以及 E2E 断言，返工面更大。

## 根因（1–3 条）

1) “终局契约”与“过渡实现”混在一个层次表达，没有显式写清实现状态与未实现门禁。
2) v0 数据源（overlay_store）并不天然具备 ledger 对齐语义，却被复用为统一读口。

## 如何避免（检查清单）

**开发前**
- [ ] 新增契约时，明确标注：目标形态 vs 当前实现状态（v0/v1）以及未实现项列表。
- [ ] 若引入 “MUST/硬门禁”，同步落一个最小可失败的测试（即使暂时 skip，也要写清触发条件）。

**开发中**
- [ ] 兼容投影端点必须在 doc 中标注为 “projection/compat”，避免下游把它当真源。
- [ ] 新接口先做 “形状一致 + 可回滚切流”，不要混入“尚未具备真源门禁”的承诺。

**验收时**
- [ ] 跑 `bash docs/scripts/doc_audit.sh`，确保文档状态一致。
- [ ] 跑最小回归：`pytest -q`、`cd frontend && npm run build`。
- [ ] 若契约包含 fail-safe，至少有 1 条测试能失败在正确位置（例如返回 `ledger_out_of_sync`）。

## 关联与证据

- 验证命令：
  - `bash docs/scripts/doc_audit.sh`
  - `pytest -q`
  - `cd frontend && npm run build`
- 关键文件：
  - `docs/core/contracts/draw_delta_v1.md`
  - `backend/app/main.py`
  - `frontend/src/widgets/ChartView.tsx`

