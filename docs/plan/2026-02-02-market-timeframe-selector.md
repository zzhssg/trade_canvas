---
title: 市场 K 线周期选择（timeframe selector）
status: 草稿
owner:
created: 2026-02-02
updated: 2026-02-02
---

## 背景

trade_canvas 需要支持用户在 Live 图表中切换周期（例如 `1m / 1h / 4h`），并且切换后：
- 历史数据读取走对应 `series_id` 的 `GET /api/market/candles`
- 实时更新走对应 `series_id` 的 `WS /ws/market subscribe`
- UI 能以“可核对的具体数值”展示最后一根 K 的关键字段（便于 E2E 验收与排障）

## 目标 / 非目标

### 目标（Do）
- 支持在 UI 选择 `timeframe`，切换后图表加载对应周期数据并继续实时跟随。
- 提供可 E2E 断言的 UI 可观测点（最后一根 K 的 time/o/h/l/c/v）。
- 保持现有对外 HTTP/WS 契约不变。

### 非目标（Don’t）
- forming K 的高频推送与展示优化（本需求只验证 closed candle）。
- replay/backtest 的策略执行逻辑改造（本需求聚焦 live chart 的周期切换链路）。

## 方案概述

- 前端：TopBar 提供 timeframe 下拉选择（沿用现有），ChartView 以 `series_id=exchange:market:symbol:timeframe` 拉取与订阅。
- 为 E2E 提供稳定断言：ChartView 将“最后一根 candle”的关键字段暴露为 DOM data-attributes。

## 任务拆解

- [ ] 添加/完善 E2E 用户故事 + E2E 测试用例（先落盘、可跑）
- [ ] 前端：给 timeframe select 增加稳定定位（data-testid）
- [ ] 前端：暴露最后一根 candle 的关键字段（data attributes）
- [ ] 前端：补 Playwright E2E 覆盖（周期切换 + WS 跟随）

## 风险与回滚

### 风险
- 若 UI 不暴露可断言的数值，E2E 只能靠网络层断言，难以满足“用户看到 X 价格”的交付要求。

### 回滚
- 可随时移除 data-attributes（不影响主功能），仅保留周期切换与现有 E2E。

## 验收标准

- 用户从 `1m` 切到 `4h` 后：
  - 触发一次 `GET /api/market/candles?series_id=...:4h`
  - UI 可观测到最后一根 K 的 `close=99999`（来自后端返回/落库数据）
- 1 分钟（或模拟事件）后触发一次“收盘事件”（HTTP ingest）：
  - 调用 `POST /api/market/ingest/candle_closed` 写入 `series_id=...:4h` 的新 candle（`open=10000`，`close=10001`，`candle_time=28800`）
  - 前端通过 `WS /ws/market` 收到 `candle_closed candle_time=28800`
  - UI 最后一根 candle 的 `open=10000`、`close=10001`（具体值可核对）

## E2E 用户故事（门禁）

### Story ID / E2E Test Case（必须）
- Story ID：`2026-02-02/market/timeframe-switch-live-follow`
- 关联 Plan：`docs/plan/2026-02-02-market-timeframe-selector.md`
- E2E 测试用例：
  - Test file path: `frontend/e2e/timeframe_selector.spec.ts`
  - Test name(s): `timeframe switch loads correct candles and follows WS`
  - Runner：Playwright

### Persona / Goal
- Persona：交易员（看盘）
- Goal：切换周期后能看到该周期历史，并持续收到新闭合 K 更新

### Entry / Exit（明确入口与出口）
- Entry：用户打开 Live 页面并切换 timeframe 为 `4h`
- Exit：UI 可观测到最后一根 candle 的字段值更新，并在 ingest 新闭合 K 后继续跟随

### Concrete Scenario（必须：写“具体数值”，禁止空泛）

- series_id：`binance:futures:BTC/USDT:4h`
- 初始状态（由测试写入）：
  - candle_time=14400, close=99999（最后一根）
- 触发事件（收盘 finalized）：
  - 写入新 candle：candle_time=28800, open=10000, close=10001
- 预期可观测结果：
  - HTTP：切换到 `4h` 后，请求 `/api/market/candles?series_id=binance:futures:BTC/USDT:4h...` 且响应最后一根 close=99999
  - WS：收到 `candle_closed`，其 `candle_time=28800`
  - UI：最后一根 candle 的 `open=10000`、`close=10001`（data-attributes 可核对）

### Preconditions（前置条件）
- 数据前置：通过 `POST /api/market/ingest/candle_closed` 注入 `1m` 与 `4h` 两套 candles
- 依赖服务：前后端联调 E2E（`bash scripts/e2e_acceptance.sh` 或单测运行 Playwright）

### Verification Commands（必须可复制运行）

- `bash scripts/e2e_acceptance.sh`
  - Expected：Playwright exit code 0，且 `output/playwright/.last-run.json` status=passed

## 交付汇报（开发完成时填）

> 按 `tc-e2e-gate` 要求：必须声明“覆盖主链路的 E2E 用例 + 具体数值 + 接口链路 + 证据路径”。

- 覆盖的主链路 E2E 用例：
  - Test file path：`frontend/e2e/timeframe_selector.spec.ts`
  - Test name：`timeframe switch loads correct candles and follows WS`
- 用户操作流程（具体）：
  1) 用户打开 Live 页面（默认 `binance:futures:BTC/USDT:1m`）。
  2) 用户在 TopBar 选择 timeframe=`4h`。
  3) 1 分钟后触发一次“收盘”（测试用例通过 HTTP ingest 模拟）。
- 触发了什么接口 / 链路：
  - `GET /api/market/candles?series_id=binance:futures:BTC/USDT:4h&limit=...` → `backend/app/main.py:get_market_candles` → `backend/app/store.py:get_closed`
  - `WS /ws/market subscribe {series_id=...:4h, since=...}` → `backend/app/main.py:ws_market` → `backend/app/ws_hub.py:CandleHub.subscribe/publish_closed`
  - `POST /api/market/ingest/candle_closed` 写入新 `candle_time=28800`（open=10000 close=10001）→ WS 推送 `candle_closed`
- 预期与结果（必须是具体数值）：
  - 切换到 `4h` 后：UI 最后一根 candle `candle_time=14400`，`open=10`，`close=99999`
  - ingest 后：UI 最后一根 candle `candle_time=28800`，`open=10000`，`close=10001`，且 `data-last-ws-candle-time=28800`
- 证据：
  - `bash scripts/e2e_acceptance.sh`（exit 0）
  - `output/playwright/.last-run.json`

## 变更记录
- 2026-02-02: 创建（草稿）
