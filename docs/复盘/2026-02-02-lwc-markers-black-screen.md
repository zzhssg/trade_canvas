---
title: 前端黑屏与图表丢失（lightweight-charts markers API 兼容性）
status: done
created: 2026-02-02
updated: 2026-02-02
---

# 前端黑屏与图表丢失（lightweight-charts markers API 兼容性）

## 背景

现象：点击左侧币种/切换面板后页面“黑屏”，拖动底部区域高度时 K 线偶发消失。

涉及链路/文件：
- `frontend/src/widgets/ChartView.tsx`（图表渲染、markers、resize）
- `frontend/src/parts/Sidebar.tsx`（左侧 Market SSE + 点击切换 symbol）
- `scripts/e2e_acceptance.sh`、`frontend/e2e/*.spec.ts`（前后端联调验收）

## 具体错误（可复现证据）

1) `lightweight-charts@5` 中蜡烛图 series 没有 `setMarkers`，但 `ChartView` 调用了它，导致运行时异常，React 组件树崩溃 → 视觉上表现为纯背景“黑屏”。
- Playwright trace 中可见 `TypeError: candleSeries.setMarkers is not a function`（堆栈指向 `ChartView.tsx`）。

2) `Sidebar` 的 SSE 连接使用了相对路径 `/api/...`，在 Vite dev server 下会打到前端端口（如 5173）→ 404，进一步放大“切换/刷新后列表不稳定”的体感问题。

3) E2E 复用/残留 server 进程会导致 Playwright 实际访问的端口漂移（如 15173/18080），造成网络请求 `ERR_FAILED`/WS 不连/用例误报。

## 影响与代价

- 主流程不可用：策略/币种切换触发“黑屏”，影响核心验收。
- 偶发/环境相关：端口漂移与 StrictMode 快速卸载重挂载使问题更难复现与定位。
- 返工成本：需要通过 trace 才能快速定位到“单行 API 不兼容”这一根因。

## 根因（1–3 条）

1) 第三方库版本升级后 API 变更，未做兼容性核对（以旧 API 代码调用新版本）。
2) API base 的约定不一致（`apiUrl/apiHttpBase` 与手写 env 拼接/相对路径混用），导致跨端口场景下请求落错目标。
3) 缺少“会失败就留证据”的回归用例（点击切换/拖拽 resize 的 UI 行为没有被 E2E 覆盖）。

## 如何避免（检查清单）

开发前：
- 对升级/引入的关键库（图表、路由、状态、请求）做一次 API diff：`rg -n "setMarkers|createSeriesMarkers" frontend/src -S`。
- 统一网络出口：前端所有 HTTP/WS/SSE 必须走 `frontend/src/lib/api.ts` 的 helper（禁止手写 base）。

开发中：
- 任何“图表渲染/指标叠加/markers”变更，至少加 1 条 UI 交互回归（切换 symbol/切换 tab/resize）。
- 处理 StrictMode 的 double-mount：避免在 create/remove 生命周期中依赖“只调用一次”的假设；必要时做 try/catch 防御。

验收时：
- 用一键验收脚本跑通 FE+BE：`bash scripts/e2e_acceptance.sh`（不要复用不明来源的残留进程）。
- 失败必须保留 trace/screenshot 并从堆栈定位到具体文件行，而不是凭直觉改动。

## 关联

- 修复文件：`frontend/src/widgets/ChartView.tsx`、`frontend/src/parts/Sidebar.tsx`
- 回归用例：`frontend/e2e/ui_clicks_no_blank.spec.ts`
- 验收命令：`bash scripts/e2e_acceptance.sh`

