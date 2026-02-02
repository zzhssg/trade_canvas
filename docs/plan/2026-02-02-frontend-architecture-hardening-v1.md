---
title: 前端架构优化 v1（contracts / chart hooks / data query / a11y）
status: 开发中
owner: rick
created: 2026-02-02
updated: 2026-02-02
---

## 背景

当前前端的核心风险点集中在：
- `frontend/src/widgets/ChartView.tsx`：职责过多（chart lifecycle + 数据同步 + overlay/markers + indicators），改动容易引入回归。
- 前后端契约重复定义（Python Pydantic vs TS type），存在漂移风险。
- 数据加载层有多套实现（SSE + 手动 fetch + 自建 cache），状态机分散，错误/加载体验不一致。
- UI 的 focus/error/loading 可观测性不足（可用性与排障成本偏高）。

## 目标 / 非目标

目标：
- 建立前后端契约的单一真源（至少做到“能自动生成/能自动校验”，避免字段漂移）。
- 继续拆分 chart 相关逻辑，降低 `ChartView` 复杂度，保证 WS/HTTP/plot 的副作用边界清晰。
- 把 Market list 的数据流统一到 React Query（同时保留 SSE 实时更新能力），减少手写 cache 与状态分叉。
- 补齐关键交互的可用性：focus ring、可见错误态、基本 loading 反馈。
- 保持 FE build + FE/BE E2E 绿（作为门禁）。

非目标：
- 不在本轮引入完整设计系统/组件库重写（只做有确定收益的结构优化与可用性补齐）。
- 不在本轮把所有 HTTP 请求都迁移到 React Query（优先从 Market list 等痛点入口做起）。

## 方案概述

1) **Contracts（单一真源）**：以 FastAPI OpenAPI 为真源，生成 TS 类型文件并在前端代码中复用。
2) **Chart 分层**：以 `widgets/chart/*` 为 domain 层；`ChartView` 只保留“组装与 UI 可观测”。
3) **Data Query 统一**：Market list 用 React Query 管理（initial fetch + SSE push 更新写入 query cache）。
4) **A11y/UX**：给主要交互加 focus-visible ring；让错误在 UI 上可见（而不是只靠 title）。

## 里程碑

- M1：OpenAPI → TS types + 前端复用
- M2：ChartView 再拆分 / overlay payload 强类型
- M3：Market list 迁移到 React Query（保留 SSE）
- M4：A11y/UX（focus/error/loading）
- M5：E2E 门禁 + 文档审计 + 交付复核

## 任务拆解（每步含验收/回滚）

1) Contracts 单一真源（OpenAPI → TS）
   - 改什么：`frontend/src/contracts/*`、生成脚本、前端引用处改为 type alias
   - 怎么验收：`npm -C frontend run build`
   - 怎么回滚：删除生成脚本与 `src/contracts/*`，恢复本地 type 定义

2) Chart 继续拆分 + 强类型 overlay payload
   - 改什么：`frontend/src/widgets/ChartView.tsx`、`frontend/src/widgets/chart/*`
   - 怎么验收：`bash scripts/e2e_acceptance.sh`（重点看 live chart/ timeframes/ ui clicks）
   - 怎么回滚：`git revert` 本次 ChartView 拆分相关 commit 或回滚到上一个可运行版本

3) Market list 数据流统一到 React Query（initial fetch + SSE 写入 cache）
   - 改什么：`frontend/src/parts/Sidebar.tsx`、新增 `frontend/src/services/*` hook（如需要）
   - 怎么验收：`bash scripts/e2e_acceptance.sh`
   - 怎么回滚：恢复 MarketPanel 的本地 state + useEffect 版本

4) UI/UX & A11y：focus/error/loading
   - 改什么：`frontend/src/parts/TopBar.tsx`、`frontend/src/parts/Sidebar.tsx`、`frontend/src/widgets/ChartView.tsx`
   - 怎么验收：E2E（`ui_clicks_no_blank`）+ 手动 tab/keyboard smoke（可选）
   - 怎么回滚：回退 className 与 UI overlay 改动

5) 门禁与证据
   - 改什么：把本计划 `status` 更新为 `已完成`，并运行 doc audit
   - 怎么验收：`bash scripts/e2e_acceptance.sh` + `bash docs/scripts/doc_audit.sh`
   - 怎么回滚：恢复文档 front matter 状态

## 风险与回滚

风险：
- OpenAPI types 生成引入新的 dev 依赖/脚本，可能导致环境差异（需要文档化）。
- React Query + SSE 的组合如果写入策略不当可能导致 UI 闪烁或 stale data（需要明确写入规则）。
- ChartView 拆分若处理不好 refs/闭包，可能出现 markers/indicators 不一致（E2E 覆盖）。

回滚策略：
- 任何“结构性重构”优先做到可一键回退（git revert 单一改动组）。
- E2E 作为硬门禁：一旦 fail，先回滚最近一步再定位（避免带病前进）。

## 验收标准

- `npm -C frontend run build` 退出码 0
- `bash scripts/e2e_acceptance.sh` 退出码 0（产物：`output/playwright/*` 与 `output/e2e_acceptance.log`）
- `bash docs/scripts/doc_audit.sh` 退出码 0

## E2E 用户故事（门禁）

### Story ID / E2E Test Case（必须）
- Story ID：`2026-02-02/frontend-arch/hardening-v1`
- 关联 Plan：`docs/plan/2026-02-02-frontend-architecture-hardening-v1.md`
- E2E 测试用例：
  - Test file path: `frontend/e2e/market_kline_sync.spec.ts`
    - Test name: `live chart loads catchup and follows WS`
  - Test file path: `frontend/e2e/timeframe_selector.spec.ts`
    - Test name: `timeframe switch loads correct candles and follows WS`
  - Test file path: `frontend/e2e/ui_clicks_no_blank.spec.ts`
    - Test name: `clicking tabs / changing symbol does not blank the app`
  - Runner：`bash scripts/e2e_acceptance.sh`（内部调用 `npm -C frontend run test:e2e`）

### Persona / Goal
- Persona：交易员/研究员（打开 Web 终端查看行情、切换周期、观察叠加/指标）
- Goal：图表能加载历史、跟随 WS 更新；切换周期/切换 symbol 不会白屏；Market list 可持续刷新

### Entry / Exit（明确入口与出口）
- Entry：打开 `http://127.0.0.1:5173/live`（或 `E2E_BASE_URL` 指定）
- Exit：
  - UI：`[data-testid="chart-view"]` 暴露的 `data-last-*` 与 `data-last-ws-candle-time` 与输入一致
  - API：`GET /api/market/candles` 返回 `series_id` 与 candle 数据符合预期
  - WS：收到 `candle_closed` 推送后 UI 更新

### Concrete Scenario（具体数值）
- series_id：`binance:futures:BTC/USDT:4h`
- 预置闭合 K（通过 ingest API 写入）：
  - candle_time=0 close=12345
  - candle_time=14400 open=10 close=99999
- 触发事件：再 ingest 一根 closed
  - candle_time=28800 open=10000 close=10001
- 预期：
  - UI `data-last-time == 28800`，`data-last-open == 10000`，`data-last-close == 10001`
  - UI `data-last-ws-candle-time == 28800`

### Main Flow（主流程步骤 + 断言）

1) Step：数据写入（mock feed）
   - Requests：`POST /api/market/ingest/candle_closed`
   - Assertions：返回 200；`GET /api/market/candles` 能读到对应 `candle_time`
   - Evidence：E2E runner 输出 + backend access log

2) Step：前端加载历史并渲染
   - Requests：`GET /api/market/candles?series_id=...`
   - Assertions：页面存在 `canvas`；`data-last-close` 匹配预置值
   - Evidence：Playwright assertions（失败有 trace/screenshot）

3) Step：WS 跟随更新
   - Requests：WS `subscribe {series_id, since}`；后续 ingest 触发 publish
   - Assertions：`data-last-ws-candle-time` 更新为新 `candle_time`
   - Evidence：Playwright assertions + `output/playwright/*`

### Produced Data（产生的数据）
- SQLite：`backend/data/market_e2e.db`
  - keys/fields：`series_id` + `candle_time` + OHLCV
  - inspect：E2E 脚本会创建并在结束后保留（用于复核）

### Verification Commands（必须可复制运行）
- `bash scripts/e2e_acceptance.sh`
  - Expected：Playwright 4 tests pass；产物 `output/playwright/.last-run.json` status=passed；doc_audit 通过

### Rollback（回滚）
- 最短回滚：`git revert` 本次变更集；删除/回退 `frontend/src/contracts/*` 与相关引用，恢复本地 type。

## 变更记录
- 2026-02-02: 创建（开发中）

