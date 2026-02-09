---
title: 彻底移除反向锚（anchor.reverse / reverse_anchor_ref）
status: done
owner: codex
created: 2026-02-08
updated: 2026-02-08
---

## 背景

- 当前反向锚把 `pen.head.candidate` 以 `anchor.reverse`（黄色虚线）额外绘制，语义与 `current_anchor_ref` 存在重叠。
- 前后端都暴露了 `anchor.reverse`/`reverse_anchor_ref`，导致契约与渲染分支增加，维护成本偏高。

## 目标 / 非目标

### 目标
- 后端不再产出 `reverse_anchor_ref`。
- overlay 不再产出 `anchor.reverse` 图元。
- 前端不再暴露 `anchor.reverse` 功能开关，且不再依赖 `reverse_anchor_ref` 渲染。
- 保持 `anchor.current`、`anchor.history`、`anchor.switch` 行为不变。

### 非目标
- 不调整 `anchor.switch` 的生成规则。
- 不改变 `pen.extending`/`pen.candidate` 的绘制规则。

## 方案概述

- 收敛 anchor 契约：`head` 仅保留 `current_anchor_ref`。
- 删除 overlay 层 `anchor.reverse` 指令生成。
- 前端高亮逻辑从“优先 reverse candidate”改为“current 为 candidate 时高亮 candidate”。
- 删除 feature catalog 与本地持久化中的 `anchor.reverse`，并在 migrate 中清理旧键。

## 里程碑

- M1 后端契约与 overlay 清理。
- M2 前端开关与渲染清理。
- M3 测试与文档同步、门禁通过。

## 任务拆解

- [x] 删除 `reverse_anchor_ref` 的生成与返回。
- [x] 删除 `anchor.reverse` overlay 产出。
- [x] 删除前端 `anchor.reverse` 子特征与状态持久化键。
- [x] 更新锚因子测试与契约文档。
- [x] 运行后端/前端/文档门禁并保留证据。

## 风险与回滚

- 风险：依赖 `reverse_anchor_ref` 的调用方将读不到该字段（契约收紧）。
- 回滚：单次原子改动可通过 `git revert <sha>` 回退。

## 验收标准

- `pytest -q` 通过。
- `cd frontend && npm run build` 通过。
- `bash scripts/e2e_acceptance.sh` 通过。
- `bash docs/scripts/doc_audit.sh` 通过。
- 全仓库不再出现 `anchor.reverse`/`reverse_anchor_ref`（迁移清理键除外）。

## E2E 用户故事（门禁）

- Persona：交易研究员在 Live 图查看锚与笔。
- Goal：在不显示反向锚的情况下，仍可查看 current/history/switch 并完成主链路观察。
- Flow：
  1) 通过行情注入让因子链路产生 `anchor.switch` 与 `pen.head.candidate`；
  2) 调用 `/api/factor/slices`，确认 `snapshots.anchor.head` 仅包含 `current_anchor_ref`；
  3) 调用 `/api/draw/delta`，确认不存在 `feature == "anchor.reverse"`；
  4) 前端加载图表，`Anchor` 面板仅包含 `Current/History/Switches`。
- 断言：
  - 反向锚字段与图元均缺失；
  - `anchor.current` 与 `anchor.history` 仍可绘制；
  - 无类型错误、构建失败、文档审计失败。

## 变更记录
- 2026-02-08: 创建并完成实现、测试与文档同步。
