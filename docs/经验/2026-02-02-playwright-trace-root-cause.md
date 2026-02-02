---
title: 用 Playwright trace 定位前端黑屏（从症状到根因）
status: done
created: 2026-02-02
updated: 2026-02-02
---

# 用 Playwright trace 定位前端黑屏（从症状到根因）

## 场景与目标

场景：点击策略/左侧币种后页面看起来“黑屏”，很难靠肉眼判断是渲染问题还是网络问题。

目标：把“黑屏”变成可复现、可定位、可回归的工程问题，并在最小改动下修复。

## 做对了什么（可复用动作/清单）

1) 先让问题可复现（而不是先改）
- 以用户动作建一个最小回归：点击 Sidebar tab、切换 symbol、切换路由，确保不出现空白页。
- 产物：`frontend/e2e/ui_clicks_no_blank.spec.ts`

2) 用 trace/网络日志定位“第一处真实错误”
- Playwright 失败时保存 trace（retain-on-failure），从 `pageError` 的 stack 直接定位到具体文件行。
- 这次根因是轻量图表库 v5 API 变化：`setMarkers` 不存在，应改用 `createSeriesMarkers` 插件 API。

3) 修复要“最小可证伪”
- 改动集中在 `ChartView`，不顺手重构其它模块。
- 同步补一条“统一 API base”的小修（SSE 也走 `apiHttpBase()`），减少跨端口误连造成的噪声。

## 为什么有效（机制/约束）

- trace 把“黑屏”还原成确定性的 JS 运行时异常（可复现、可定位、可回归）。
- 回归用例把“修好一次”变成“以后改坏会立刻红灯”。
- 统一 `apiHttpBase/apiUrl` 让跨端口/部署环境下的请求更稳定，减少非功能性波动。

## 复用方式（下次如何触发/在哪个阶段用）

- 任何“UI 黑屏/整页空白/偶发消失”问题：优先写 1 条最小 UI 交互 e2e + 打开 trace。
- 任何“图表类库/渲染层”升级：先确认关键 API（markers/resize/websocket）是否变更，再写回归。

## 关联

- 核心修复：`frontend/src/widgets/ChartView.tsx`（markers 改为 `createSeriesMarkers`）
- SSE base 修复：`frontend/src/parts/Sidebar.tsx`（统一走 `apiHttpBase()`）
- 验证命令：`bash scripts/e2e_acceptance.sh`

