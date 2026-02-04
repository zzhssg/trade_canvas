---
title: Chart fitContent 导致 K 线“巨粗”回归
status: done
created: 2026-02-02
updated: 2026-02-02
tags: [frontend, chart, lightweight-charts, regression]
---

# 背景

在 Live 图表刷新/重连（出现缺数据、只拉到少量 K 线）时，K 线会突然变得非常大（barSpacing 飙高），影响读图与交互。

涉及链路/文件：

- 图表渲染与数据刷新：`frontend/src/widgets/ChartView.tsx`
- 图表初始化：`frontend/src/widgets/chart/useLightweightChart.ts`

# 具体错误（可复现现象/证据）

- 触发条件：刷新后只得到很少的 candle（例如后端短暂缺数据、或前端只拿到尾部极少条）。
- 现象：调用 `timeScale().fitContent()` 后，`barSpacing` 被自动拉得很大，导致蜡烛“巨粗/巨大”。
- 证据点位：`ChartView` 上的 `data-bar-spacing`（用于观测）在此情况下异常偏大。

# 影响与代价

- 读图误导：用户误以为“行情剧烈波动/蜡烛异常”，实际是视图缩放问题。
- 操作成本：需要手动缩放回正常视图，且每次刷新可能复发。

# 根因（1–3 条）

1) `fitContent()` 的视觉策略在“数据点很少”时会扩大 `barSpacing` 来铺满视窗，这是库的合理行为，但在缺数据场景下会产生反直觉效果。
2) 刷新链路中会先清空再 setData + fitContent，放大了“短暂稀疏窗口”的影响。

# 如何避免（检查清单）

开发前（3–5 条）：

- 明确 UI 需要在“稀疏数据/空数据/断流重连”下的 fail-safe 行为。
- 对所有会触发 `fitContent()` 的路径列出清单（初始化、切品种、重连、回放跳转）。
- 约定并记录一个“可接受的 barSpacing 上限”作为 UX 不变量。

开发中（3–5 条）：

- `fitContent()` 后立刻读取 `timeScale().options().barSpacing`，在异常时 clamp（仅限自动 fit，不影响用户手动缩放）。
- 把 clamp 逻辑做成可复用工具函数，避免散落多处不一致。
- 用一个可自动运行的小脚本/断言锁住 clamp 行为。

验收时（3–5 条）：

- 用“只有 1–3 根 K 线”的场景验收：刷新/重连/切周期后仍应保持可读。
- 观测点：`data-bar-spacing` 不应超过约定上限。
- 跑 `cd frontend && npm run build`，避免 TS/打包回归。

# 关联（文件/验证命令）

- 修复：`frontend/src/widgets/ChartView.tsx`
- 工具：`frontend/src/widgets/chart/barSpacing.ts`
- 回归脚本：`node frontend/scripts/test-bar-spacing.mjs`
