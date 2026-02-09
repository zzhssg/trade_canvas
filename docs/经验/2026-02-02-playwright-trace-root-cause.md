---
title: "用 Playwright trace 定位前端黑屏（LWC markers API 兼容性）"
status: done
created: 2026-02-02
updated: 2026-02-09
---

# 用 Playwright trace 定位前端黑屏（LWC markers API 兼容性）

## 问题背景

点击左侧币种/切换面板后页面"黑屏"，拖动底部区域高度时 K 线偶发消失。

具体错误：
1. `lightweight-charts@5` 中蜡烛图 series 没有 `setMarkers`，但 `ChartView` 调用了它，导致运行时异常 `TypeError: candleSeries.setMarkers is not a function`，React 组件树崩溃表现为纯背景"黑屏"。
2. `Sidebar` 的 SSE 连接使用了相对路径 `/api/...`，在 Vite dev server 下打到前端端口 404，放大"切换/刷新后列表不稳定"的体感。
3. E2E 复用/残留 server 进程导致 Playwright 实际访问的端口漂移，造成网络请求 `ERR_FAILED`/WS 不连/用例误报。

## 根因

1. 第三方库版本升级后 API 变更，未做兼容性核对（以旧 API 代码调用新版本）。
2. API base 约定不一致（`apiUrl/apiHttpBase` 与手写 env 拼接/相对路径混用），导致跨端口场景下请求落错目标。
3. 缺少"会失败就留证据"的回归用例（点击切换/拖拽 resize 的 UI 行为没有被 E2E 覆盖）。

## 解法

1. **先让问题可复现**（而不是先改）：以用户动作建一个最小回归（点击 Sidebar tab、切换 symbol、切换路由），产物：`frontend/e2e/ui_clicks_no_blank.spec.ts`。
2. **用 trace/网络日志定位"第一处真实错误"**：Playwright 失败时保存 trace（retain-on-failure），从 `pageError` 的 stack 直接定位到具体文件行。根因是 LWC v5 API 变化：`setMarkers` 不存在，应改用 `createSeriesMarkers` 插件 API。
3. **修复要"最小可证伪"**：改动集中在 `ChartView`，不顺手重构其它模块。同步补一条"统一 API base"的小修（SSE 也走 `apiHttpBase()`）。

## 为什么有效

- trace 把"黑屏"还原成确定性的 JS 运行时异常（可复现、可定位、可回归）。
- 回归用例把"修好一次"变成"以后改坏会立刻红灯"。
- 统一 `apiHttpBase/apiUrl` 让跨端口/部署环境下的请求更稳定。

## 检查清单

**开发前**
- [ ] 对升级/引入的关键库（图表、路由、状态、请求）做一次 API diff：`rg -n "setMarkers|createSeriesMarkers" frontend/src -S`。
- [ ] 统一网络出口：前端所有 HTTP/WS/SSE 必须走 `frontend/src/lib/api.ts` 的 helper（禁止手写 base）。

**开发中**
- [ ] 任何"图表渲染/指标叠加/markers"变更，至少加 1 条 UI 交互回归（切换 symbol/切换 tab/resize）。
- [ ] 处理 StrictMode 的 double-mount：避免在 create/remove 生命周期中依赖"只调用一次"的假设。
- [ ] 任何"UI 黑屏/整页空白/偶发消失"问题：优先写 1 条最小 UI 交互 e2e + 打开 trace。

**验收时**
- [ ] 用一键验收脚本跑通 FE+BE：`bash scripts/e2e_acceptance.sh`（不要复用不明来源的残留进程）。
- [ ] 失败必须保留 trace/screenshot 并从堆栈定位到具体文件行。

## 关联

- `frontend/src/widgets/ChartView.tsx`（markers 改为 `createSeriesMarkers`）
- `frontend/src/parts/Sidebar.tsx`（统一走 `apiHttpBase()`）
- `frontend/e2e/ui_clicks_no_blank.spec.ts`
- 验收命令：`bash scripts/e2e_acceptance.sh`
