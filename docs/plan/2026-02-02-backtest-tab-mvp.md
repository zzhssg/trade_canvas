---
title: Backtest bottom tab MVP（freqtrade）
status: done
owner: codex
created: 2026-02-02
updated: 2026-02-02
---

## 背景

当前 trade_canvas 已有后端 backtest API 与独立 `/backtest` 页面，但核心工作流是“看 K 线 → 选策略 → 回测 → 看结果”。本计划把回测能力落到 **K 线图下方的 BottomTabs** 中，形成更自然的研究闭环。

## 目标 / 非目标

### 目标
- 在 K 线图下方 BottomTabs 增加 `Backtest` tab。
- `Backtest` tab 内提供策略列表（来自后端 `/api/backtest/strategies`）。
- 可选择策略并触发后端 `/api/backtest/run` 执行 freqtrade 回测。
- 在同一个 tab 内打印回测 stdout/stderr（可复制）。
- 提供可重复的 Playwright E2E（不依赖本机真实 freqtrade 数据与策略目录）。

### 非目标
- 不做回测结果结构化展示（表格/图表/指标拆解）。
- 不做异步任务队列、取消、进度条、流式日志（首期仅请求-响应）。
- 不保证本机已安装 freqtrade 或具备历史数据；E2E 仅覆盖 wiring 与输出渲染。

## 方案概述

- 前端：抽出可复用 `BacktestPanel`，用于 `/backtest` 页面与 BottomTabs 的 `Backtest` tab。
- 后端：保留真实 freqtrade 执行逻辑；新增 `TRADE_CANVAS_FREQTRADE_MOCK=1` 时的 mock 响应，用于 E2E 稳定运行。
- E2E：新增 Playwright 用例，覆盖 “Live → Backtest tab → Run → Output 可见” 主链路断言。

## 任务拆解（每步都可验收/可回滚）

1) 前端 BacktestPanel + BottomTabs 集成  
   - 改什么：`frontend/src/parts/BottomTabs.tsx`、`frontend/src/pages/BacktestPage.tsx`、新增 `frontend/src/parts/BacktestPanel.tsx`、`frontend/src/state/uiStore.ts`  
   - 怎么验收：`cd frontend && npm run build`  
   - 怎么回滚：`git revert`（或从 BottomTabs 移除 `Backtest` tab）

2) 后端 freqtrade mock mode（仅用于 E2E）  
   - 改什么：`backend/app/main.py`、`scripts/e2e_acceptance.sh`  
   - 怎么验收：`pytest -q`  
   - 怎么回滚：移除 `TRADE_CANVAS_FREQTRADE_MOCK` 分支与脚本 export

3) 新增 E2E（主链路门禁）  
   - 改什么：新增 `frontend/e2e/backtest_tab.spec.ts`  
   - 怎么验收：`E2E_PLAN_DOC="docs/plan/2026-02-02-backtest-tab-mvp.md" bash scripts/e2e_acceptance.sh`  
   - 怎么回滚：删除该 spec 并恢复旧 UI（不建议）

## 风险与回滚

- 风险：本机 freqtrade 环境不一致导致回测不可用。  
  - 处理：E2E 使用 mock mode；真实环境仍保留原有 freqtrade 执行路径。
- 风险：BottomTabs 变复杂影响其他页面体验。  
  - 处理：BacktestPanel 做成独立组件；必要时可以 feature flag 隐藏 Backtest tab。

## 验收标准

- 必要门禁：
  - `pytest -q`
  - `cd frontend && npm run build`
  - `E2E_PLAN_DOC="docs/plan/2026-02-02-backtest-tab-mvp.md" bash scripts/e2e_acceptance.sh`（exit 0，产物在 `output/playwright/`）

## E2E 用户故事（门禁）

**Persona**：量化研究员（使用 trade_canvas 看盘与验证策略）  
**Goal**：在看 K 线时直接选择策略并运行一次回测，看到 freqtrade 输出结果  

### Steps + Assertions（可自动化）

1) 打开 `Live` 页面并看到 K 线 chart canvas  
   - 断言：`[data-chart-area="true"] canvas` 可见
2) 在 K 线下方 BottomTabs 点击 `Backtest`  
   - 断言：`[data-testid="backtest-panel"]` 可见
3) 策略列表加载并包含 `DemoStrategy`（mock mode）  
   - 断言：`[data-testid="backtest-strategy-select"]` options 包含 `DemoStrategy`
4) 输入 timerange（例如 `20260130-20260201`），点击 `Run backtest`  
   - 断言：请求命中 `/api/backtest/run`，返回 `ok=true`
5) 输出区域展示回测报告文本  
   - 断言：`[data-testid="backtest-output"]` 包含 `TRADE_CANVAS MOCK BACKTEST` 且包含 pair/timeframe/timerange

## 变更记录

- 2026-02-02: 创建并完成（MVP）

