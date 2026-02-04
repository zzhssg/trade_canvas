---
title: 右侧 Debug Tab（读写链路日志）
status: 草稿
owner:
created: 2026-02-04
updated: 2026-02-04
---

## 背景

排障时需要把“读链路/写链路”的关键节点变成可观测证据：一次性加载、回放加载、WS 新 K 线、ingest 写入与派生补全（factor/overlay/plot）。

## 目标 / 非目标

### 目标
- UI 右侧 Sidebar 增加 `Debug` tab，显示实时调试日志。
- 后端提供 `WS /ws/debug`，支持 snapshot + streaming。
- 首期只做关键事件（避免刷屏）。

### 非目标
- 不做复杂的日志结构化查询/持久化。
- 不做“生产默认开启”。

## E2E 用户故事

### Story ID / E2E Test Case
- Story ID：`2026-02-04/debug-tab/logs`
- E2E 测试用例：Playwright
  - Test file path: `frontend/e2e/debug_tab_logs.spec.ts`
  - Test name: `live debug tab shows read+write logs`

### Persona / Goal
- Persona：开发/排障工程师
- Goal：在 UI 中看到读/写链路关键日志，用于定位链路断点与时序问题。

### Concrete Scenario（具体数值）
- series_id：`binance:futures:BTC/USDT:5m`
- 预置写入：
  - candle_time=300, close=1
- 触发：
  - 打开 `/live`，切换到右侧 `Debug` tab
  - 再 ingest 新 candle_time=600
- 预期：
  - Debug 面板能看到 `read.*`（例如 `read.http.market_candles` / `read.ws.market_*`）
  - Debug 面板能看到 `write.http.ingest_candle_closed_done`（至少 2 条：预置 + 追加）

## 验收标准
- `pytest -q`
- `cd frontend && npm run build`
- `bash docs/scripts/doc_audit.sh`
- Playwright：新增用例通过（包含“能失败”的断言：读+写日志都出现）

## 回滚
- 前端：`VITE_ENABLE_DEBUG_TOOL=0`（隐藏 Debug tab）
- 后端：`TRADE_CANVAS_ENABLE_DEBUG_API=0`（禁用 /ws/debug）
