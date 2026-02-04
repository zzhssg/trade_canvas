---
title: 中间区域可滚动（且底部 Tabs 固定在图下方）
status: 已完成
owner:
created: 2026-02-02
updated: 2026-02-02
---

## 背景

中间内容区域（K 线图所在区域）需要支持滚动；同时底部 `BottomTabs`（含 Backtest tab）必须固定在 K 线图下方，不能被滚动带走。

## 目标 / 非目标

- 目标
  - 中间区域可滚动（当内容超出可视高度时）。
  - 底部 `BottomTabs` 在 K 线图下方，随中间区域滚动“划上来”（可滚动到看到）。
  - 鼠标在 K 线图中滚动：横向缩放图表（bar spacing 变化），且不滚动中间区域。
  - 鼠标在图表外滚动：滚动中间区域，且不触发图表缩放。
  - UI 下拉菜单（Factors 子菜单）不被 K 线遮挡。
- 非目标
  - 不改任何业务功能/数据流/接口。

## 验收标准

- `middle-scroll` 容器可滚动（scrollTop 可变化，且 scrollHeight > clientHeight）。
- 滚动中间区域后，可以滚动到看到 `bottom-tabs`。
- 仅当鼠标悬停在图表区域时，滚轮会改变图表的 `data-bar-spacing`（缩放），且不会改变 `middle-scroll` 的 scrollTop。
- 鼠标不在图表区域时，滚轮会改变 `middle-scroll` 的 scrollTop，且不会改变图表的 `data-bar-spacing`。

## E2E 用户故事（门禁）

Persona：使用者在查看 K 线图与指标时，需要在不丢失底部工具区的情况下滚动页面内容。

Steps / Assertions：
1) 打开 `Live` 页面（包含 K 线图）。
2) 在 `middle-scroll` 中注入一段超长内容，使页面有可滚动空间，并验证能滚动到看到 `bottom-tabs`。
3) 鼠标悬停在图表区域滚轮：断言 `data-bar-spacing` 发生变化（横向缩放），且 `middle-scroll` 的 `scrollTop` 不变。
4) 鼠标悬停在图表外（例如 Factors 区域）滚轮：断言 `middle-scroll` 的 `scrollTop` 变大，且 `data-bar-spacing` 不变。

Test file：
- `frontend/e2e/layout_middle_scroll.spec.ts`
- `frontend/e2e/chart_wheel_behavior.spec.ts`

验证命令：
- 快速本地：`cd frontend && npm run test:e2e -- e2e/layout_middle_scroll.spec.ts`
- 快速本地（滚轮）：`cd frontend && npm run test:e2e -- e2e/chart_wheel_behavior.spec.ts`
- 集成门禁：`bash scripts/e2e_acceptance.sh --smoke --skip-doc-audit -- --grep @smoke`
