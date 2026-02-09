---
title: "交互契约先落盘再迭代（wheel/scroll 防回归）"
status: 已完成
created: 2026-02-03
updated: 2026-02-09
---

# 交互契约先落盘再迭代（wheel/scroll 防回归）

## 问题背景

在前端做「K 线滚轮缩放 + 中间区域滚动 + BottomTabs 可滚动到出现 + 隐藏滚动条」这一组体验优化时，多次出现"改了新需求把老需求弄丢"的回归。

具体错误：
1. **需求口径漂移**：对"BottomTabs 在图下方"的理解从「固定底部面板」和「随中间区域滚动划上来」来回切换，造成结构反复重构。
2. **wheel 事件理解偏差**：一开始假设 "wheel over chart 应该滚动页面" 与 "wheel over chart 应该缩放图表" 互相冲突，导致实现/测试不断推倒重来。
3. **回归保护缺失**：在没有明确 E2E 断言之前，凭肉眼/局部组件判断"差不多"，结果多次返工。

## 根因

1. **没有先写清行为契约**：滚动/缩放属于交互契约，缺少单一真源（E2E story + 可跑用例）。
2. **缺少"必须同时满足"的门禁**：中间可滚动、图内缩放、图外滚动、BottomTabs 可达，这些是组合约束，单点验证不够。
3. **事件路由复杂**：LWC 对 wheel 的拦截 + hover-lock，天然容易出现边界 case。

## 解法

- **把交互拆成 2 条互斥规则**：
  1. 图表区域内滚轮：横向缩放图表（`barSpacing` 变化），不滚动页面。
  2. 图表区域外滚轮：滚动中间区域（`scrollTop` 变化），不改变图表 `barSpacing`。
- **用 E2E 把规则写死**：`chart_wheel_behavior` 对比 `data-bar-spacing` 与 `middle-scroll.scrollTop`；`layout_middle_scroll` 能滚动到看到 `bottom-tabs`。
- **用 hover lock 明确状态机**：由 `data-chart-area="true"` 的 `onMouseEnter/Leave` 控制锁定。

## 为什么有效

- UI 交互属于"隐式契约"，没有测试就会漂移；E2E 用可观测数据属性（`data-*`）把契约变成可验收事实。
- 规则互斥 + 单点裁决（hover lock）能避免"两个地方都想处理 wheel"导致不可预期。

## 检查清单

**开发前**
- [ ] 写清楚"图内/图外 wheel"的规则与边界（尤其是 hover lock 是否启用）。
- [ ] 明确 BottomTabs 的语义：固定面板 vs 中间滚动内容的一部分（只选一种）。
- [ ] 先加一个能失败的 E2E（最小断言：barSpacing 变化 + scrollTop 变化 + bottom-tabs 可达）。

**开发中**
- [ ] 任何改动都以 E2E 断言为中心推进，不做"凭感觉的重构"。
- [ ] UI 事件（wheel/scroll/hover lock）只允许在一个层级做"裁决"。
- [ ] 每次改动后跑：`cd frontend && npm run build`。

**验收时**
- [ ] 跑门禁脚本并留证据：`bash scripts/e2e_acceptance.sh --smoke --skip-doc-audit -- --grep @smoke`。
- [ ] 必须回放两种场景：图内滚轮缩放、图外滚轮滚动到看到 BottomTabs。
- [ ] 如果用户口径变化，先更新 plan / E2E 断言，再改代码（禁止先改代码）。

## 关联

- `frontend/src/layout/AppShell.tsx`
- `frontend/src/parts/ChartPanel.tsx`
- `frontend/src/widgets/ChartView.tsx`
- `frontend/e2e/chart_wheel_behavior.spec.ts`
- `frontend/e2e/layout_middle_scroll.spec.ts`
