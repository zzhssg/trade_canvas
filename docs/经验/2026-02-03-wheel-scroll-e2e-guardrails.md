---
title: 交互契约先落盘（wheel/scroll）再迭代，实现不漂移
status: 已完成
owner:
created: 2026-02-03
updated: 2026-02-03
---

## 场景与目标

场景：同一页面同时存在 “图表缩放” 与 “页面滚动”，且底部有可切换的 Tabs（Backtest 等）。

目标：把交互规则固定成可验收的真源，避免“改一个点，另一个点悄悄回归”。

## 做对了什么（可复用动作/清单）

- **把交互拆成 2 条互斥规则**：
  1) 图表区域内滚轮：横向缩放图表（`barSpacing` 变化），不滚动页面。
  2) 图表区域外滚轮：滚动中间区域（`scrollTop` 变化），不改变图表 `barSpacing`。
- **用 E2E 把规则写死**：
  - `chart_wheel_behavior`：对比 `data-bar-spacing` 与 `middle-scroll.scrollTop`
  - `layout_middle_scroll`：能滚动到看到 `bottom-tabs`
- **用 hover lock 明确状态机**：由 `data-chart-area="true"` 的 `onMouseEnter/Leave` 控制锁定（禁止在多个层级同时拦截 wheel）。

## 为什么有效（机制/约束）

- UI 交互属于“隐式契约”，没有测试就会漂移；E2E 用可观测数据属性（`data-*`）把契约变成可验收事实。
- 规则互斥 + 单点裁决（hover lock）能避免“两个地方都想处理 wheel”导致不可预期。

## 复用方式（下次如何触发/在哪个阶段用）

触发条件：任何涉及以下内容的改动都必须复用本清单
- 页面滚动容器（AppShell / middle scroll）
- 图表 wheel 行为（缩放/滚动/阻止默认）
- BottomTabs/Backtest 的布局与滚动语义

建议流程：
1) 先更新 `docs/plan/...` 的验收断言（若口径变化）。
2) 跑快速门禁：`bash scripts/e2e_acceptance.sh --smoke --skip-doc-audit -- --grep @smoke`
3) 再做 UI 微调/重构。

## 关联

- 关键实现：
  - `frontend/src/layout/AppShell.tsx`
  - `frontend/src/parts/ChartPanel.tsx`
  - `frontend/src/widgets/ChartView.tsx`
- 回归用例：
  - `frontend/e2e/chart_wheel_behavior.spec.ts`
  - `frontend/e2e/layout_middle_scroll.spec.ts`

