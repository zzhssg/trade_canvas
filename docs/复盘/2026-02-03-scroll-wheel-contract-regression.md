---
title: 滚轮/滚动行为反复漂移（缺少门禁导致返工）
status: 已完成
owner:
created: 2026-02-03
updated: 2026-02-03
---

## 背景

在前端做「K 线滚轮缩放 + 中间区域滚动 + BottomTabs 可滚动到出现 + 隐藏滚动条」这一组体验优化时，多次出现“改了新需求把老需求弄丢”的回归（例如中间区域不再可滚动 / 回测区变成固定面板 / wheel 行为被图表拦截）。

涉及文件/链路（证据）：
- `frontend/src/layout/AppShell.tsx`（中间滚动容器与 BottomTabs 放置）
- `frontend/src/parts/ChartPanel.tsx`（图表区域 hover lock/unlock）
- `frontend/src/widgets/ChartView.tsx`（图表内 wheel 横向缩放）
- `frontend/src/widgets/chart/useLightweightChart.ts`（LWC wheel 配置）

## 具体错误（可复现现象）

1) **需求口径漂移**：对“BottomTabs 在图下方”的理解从「固定底部面板」↔「随中间区域滚动划上来」来回切换，造成结构反复重构。
2) **wheel 事件理解偏差**：一开始假设 “wheel over chart 应该滚动页面” 与 “wheel over chart 应该缩放图表” 互相冲突，导致实现/测试不断推倒重来。
3) **回归保护缺失**：在没有明确 E2E 断言之前，凭肉眼/局部组件判断“差不多”，结果多次返工。

## 影响与代价

- 反复改 `AppShell` 的滚动/布局，增加了未来理解成本与 bug 诱因。
- 频繁调整 wheel 逻辑，导致 UI 体感不稳定（“忽快忽慢/忽缩放忽滚动”）。
- 测试与实现来回追赶，浪费时间。

## 根因（1–3 条）

- **没有先写清行为契约**：滚动/缩放属于交互契约，缺少单一真源（E2E story + 可跑用例）。
- **缺少“必须同时满足”的门禁**：中间可滚动、图内缩放、图外滚动、BottomTabs 可达，这些是组合约束，单点验证不够。
- **事件路由复杂**：LWC 对 wheel 的拦截 + 我们的 hover-lock，天然容易出现边界 case（selector/hover 状态/平台差异）。

## 如何避免（检查清单）

### 开发前（3–5 条）
- 写清楚“图内/图外 wheel”的规则与边界（尤其是 hover lock 是否启用）。
- 明确 BottomTabs 的语义：**固定面板** vs **中间滚动内容的一部分**（只选一种）。
- 先加一个能失败的 E2E（最小断言：barSpacing 变化 + scrollTop 变化 + bottom-tabs 可达）。

### 开发中（3–5 条）
- 任何改动都以 E2E 断言为中心推进，不做“凭感觉的重构”。
- UI 事件（wheel/scroll/hover lock）只允许在一个层级做“裁决”（避免多个地方同时拦截）。
- 每次改动后跑：`cd frontend && npm run build`。

### 验收时（3–5 条）
- 跑门禁脚本并留证据：`bash scripts/e2e_acceptance.sh --smoke --skip-doc-audit -- --grep @smoke`
- 必须回放两种场景：图内滚轮缩放、图外滚轮滚动到看到 BottomTabs。
- 如果用户口径变化，先更新 plan / E2E 断言，再改代码（禁止先改代码）。

## 关联

- 回归门禁用例：`frontend/e2e/chart_wheel_behavior.spec.ts`、`frontend/e2e/layout_middle_scroll.spec.ts`
- 计划/真源：`docs/plan/2026-02-02-layout-middle-scroll-e2e-gate.md`

