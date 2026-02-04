---
title: 图表 fitContent 的稀疏数据护栏（barSpacing clamp）
status: done
created: 2026-02-02
updated: 2026-02-02
tags: [frontend, chart, lightweight-charts, guardrail]
---

# 场景与目标

场景：市场数据短暂缺失/重连后只拉到很少 candle 时，`fitContent()` 会把 `barSpacing` 拉得很大，造成“蜡烛巨粗”的视觉异常。

目标：只对“自动 fit”加护栏，避免破坏用户手动缩放体验。

# 做对了什么（可复用动作）

- 只在 `fitContent()` 之后 clamp `barSpacing`（不干预用户鼠标/手势缩放）。
- 将 clamp 抽成独立小模块，便于复用与统一阈值：
  - `frontend/src/widgets/chart/barSpacing.ts`
- 用一个 Node 脚本做最小回归保护（无需引入新的测试框架）：
  - `frontend/scripts/test-bar-spacing.mjs`

# 为什么有效（机制/约束）

- `fitContent()` 是“库自动计算视图”的入口，稀疏数据下的极端 `barSpacing` 在这里被截断；
- 仅在自动 fit 场景生效，用户主动 zoom 仍然保留原生交互自由度。

# 复用方式（下次如何触发）

当你发现 UI 在“缺数据/极少数据/断流”下出现极端缩放、极端 padding、极端 axis range：

- 先找出“自动布局/自动缩放”的入口（如 fitContent/autoScale）；
- 在入口之后加 clamp，并补一个“能失败的”回归脚本/断言。

# 关联（路径/命令）

- 关键代码：`frontend/src/widgets/ChartView.tsx`
- 验证命令：
  - `node frontend/scripts/test-bar-spacing.mjs`
  - `cd frontend && npm run build`
