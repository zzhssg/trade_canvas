---
title: "图表 fitContent 稀疏数据护栏（barSpacing clamp）"
status: done
created: 2026-02-02
updated: 2026-02-09
---

# 图表 fitContent 稀疏数据护栏（barSpacing clamp）

## 问题背景

Live 图表刷新/重连时（出现缺数据、只拉到少量 K 线），K 线会突然变得非常大（barSpacing 飙高），影响读图与交互。

触发条件：刷新后只得到很少的 candle（后端短暂缺数据、或前端只拿到尾部极少条）。现象：调用 `timeScale().fitContent()` 后，`barSpacing` 被自动拉得很大，导致蜡烛"巨粗/巨大"。证据：`ChartView` 上的 `data-bar-spacing` 在此情况下异常偏大。

涉及文件：`frontend/src/widgets/ChartView.tsx`、`frontend/src/widgets/chart/useLightweightChart.ts`。

## 根因

1. `fitContent()` 的视觉策略在"数据点很少"时会扩大 `barSpacing` 来铺满视窗，这是库的合理行为，但在缺数据场景下产生反直觉效果。
2. 刷新链路中会先清空再 setData + fitContent，放大了"短暂稀疏窗口"的影响。

## 解法

- 只在 `fitContent()` 之后 clamp `barSpacing`（不干预用户鼠标/手势缩放）。
- 将 clamp 抽成独立小模块，便于复用与统一阈值：`frontend/src/widgets/chart/barSpacing.ts`。
- 用 Node 脚本做最小回归保护（无需引入新测试框架）：`frontend/scripts/test-bar-spacing.mjs`。

## 为什么有效

- `fitContent()` 是"库自动计算视图"的入口，稀疏数据下的极端 `barSpacing` 在这里被截断。
- 仅在自动 fit 场景生效，用户主动 zoom 仍保留原生交互自由度。

## 检查清单

**开发前**
- [ ] 明确 UI 在"稀疏数据/空数据/断流重连"下的 fail-safe 行为。
- [ ] 对所有会触发 `fitContent()` 的路径列出清单（初始化、切品种、重连、回放跳转）。
- [ ] 约定并记录一个"可接受的 barSpacing 上限"作为 UX 不变量。

**开发中**
- [ ] `fitContent()` 后立刻读取 `timeScale().options().barSpacing`，在异常时 clamp（仅限自动 fit，不影响用户手动缩放）。
- [ ] 把 clamp 逻辑做成可复用工具函数，避免散落多处不一致。

**验收时**
- [ ] 用"只有 1-3 根 K 线"的场景验收：刷新/重连/切周期后仍应保持可读。
- [ ] 观测点：`data-bar-spacing` 不应超过约定上限。
- [ ] `node frontend/scripts/test-bar-spacing.mjs`
- [ ] `cd frontend && npm run build`

**复用触发**：当 UI 在"缺数据/极少数据/断流"下出现极端缩放/极端 padding/极端 axis range 时，先找出"自动布局/自动缩放"的入口（如 fitContent/autoScale），在入口之后加 clamp 并补回归。

## 关联

- `frontend/src/widgets/ChartView.tsx`
- `frontend/src/widgets/chart/barSpacing.ts`
- `frontend/scripts/test-bar-spacing.mjs`
