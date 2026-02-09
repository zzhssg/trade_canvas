---
title: 市场 K 线：一次加载历史 + WS 推送 forming（未收线跳动）
status: 草稿
owner: rick
created: 2026-02-02
updated: 2026-02-08
---

## 背景

目前前端 `ChartView` 的同步策略是：

1) HTTP 拉最近 `limit=2000`（tail）快速出图；  
2) 再用 HTTP `since=<cursor>&limit=5000` 做 catchup（补齐到 `server_head_time`）；  
3) 再通过 `WS /ws/market` 跟随 `candle_closed`（闭合 K）。

这会带来两个问题：

- 网络层可见两次 HTTP `/api/market/candles`（用户期望“一次加载历史”）。
- WS 目前只推送 `candle_closed`，图表最后一根“未收线 K”不会跳动（forming 只存在于文档语义层，未落地实现）。

参考语义约束（必须保持）：`docs/core/market-kline-sync.md`（closed 为权威输入，forming 仅用于显示，不入库/不进因子引擎）。

---

## 目标 / 非目标

### 目标

1) **一次性加载历史数据**：每次切换 `series_id`，最多一次 HTTP 拉历史（不再额外 HTTP catchup probe）。  
2) **WS 跟随闭合 + forming 跳动**：WS 持续推送 `candle_closed`，并额外推送 `forming` 更新，让图表最后一根未收线 K 跳动。  
3) **兼容降级**：没有 forming 来源时（例如 `ccxt` 模式），系统仍可只在收线时更新（不报错）。

### 非目标

- 不让 forming 进入 SQLite 真源；不让 forming 进入因子引擎/策略信号。
- 不追求 tick 级/交易级推送；forming 推送允许节流（例如 250–1000ms）。
- v1 不强制把“历史快照”也改成 WS-only（可作为 v2 优化）。

---

## 方案概述

### A. 前端：只做一次 HTTP + WS 兜底补齐

调整 `frontend/src/widgets/ChartView.tsx` 的同步流程为：

1) **HTTP 一次拉历史**：`GET /api/market/candles?series_id=...&limit=2000`（只保留这一条）。  
2) **建立 WS 并 subscribe**：发送 `subscribe { series_id, since: <last_closed_time> }`。  
3) **依赖 WS catchup + gap**：
   - 服务端在 subscribe 时已实现“从 since 推送 catchup closed candles”（`backend/app/main.py`），可覆盖 HTTP 与 WS 之间的竞态窗口。
   - 服务端若发现缺口会发送 `gap`，前端收到后再触发一次 HTTP 增量补齐（只在异常/缺口时发生）。

结果：常态只有 1 次 HTTP；后续仅 WS。

### B. 后端：增加 forming 事件（WS-only），并节流

新增 WS 消息类型（v1）：

- `candle_forming { series_id, candle }`
  - `candle` 结构与 `CandleClosed` 一致（`candle_time/open/high/low/close/volume`），但语义是“未闭合/可变”。
  - forming 不写入 SQLite，仅广播给订阅者。

forming 数据来源策略（v1，2026-02-08 后）：

- 当前仅保留 `backend/app/ingest_binance_ws.py` 实时链路：
  - 解析 Binance kline payload 中 `x=false` 的更新（未闭合 kline），并作为 forming 广播。
  - `x=true`（闭合）仍走现有闭合逻辑：落库 + `candle_closed` 广播。

节流（必须）：

- 增加 env 控制（建议默认 250ms）：`TRADE_CANVAS_MARKET_FORMING_MIN_INTERVAL_MS=250`
- 对每个 `series_id` 至少保证：
  - 频率受控（避免 UI/state 高频更新与 WS 压力）。
  - 仅当 forming candle_time 匹配当前 timeframe 的 open_time 时推送；跨 candle_time 的 forming 视为“新一根 forming”。

### C. 合并策略（前端）

前端合并规则（只用 `candle_time` 主键）：

- 收到 `candle_forming`：如果 `candle_time` 等于当前最后一根 time，则更新最后一根；如果大于最后一根，则 append 新 forming。
- 收到 `candle_closed`：同 `candle_time` 覆盖 forming（closed 为权威），如果大于最后一根则 append。

`mergeCandle` 已具备“同 time 覆盖”的语义，可复用。

---

## 里程碑

### M1（v1）：一次 HTTP + WS forming

- 前端移除“HTTP catchup probe 循环”，只保留一次历史拉取。
- 后端增加 `candle_forming` WS 事件（binance_ws 模式可用），并节流。
- E2E 覆盖：验证一次 HTTP + WS 收到 forming 并导致图表最后一根变化。

### M2（v2，可选）：WS snapshot（彻底零 HTTP）

- `subscribe` 支持 `tail_limit`，服务端返回 `snapshot { candles[], server_head_time, forming? }`，之后只推 delta。
- 前端完全不走 `/api/market/candles`（或仅用于 debug）。

---

## 任务拆解

### 1) 前端：移除 HTTP catchup probe（保留 WS catchup/gap）

- **改什么**
  - `frontend/src/widgets/ChartView.tsx`：删除/收敛 `for (;;)` 的 HTTP catchup 循环；WS `gap` 时再走一次 HTTP 增量补齐即可。
- **怎么验收**
  - 打开 chart 页面，Network 里 `/api/market/candles` 对同一个 `series_id` 只出现一次（正常路径）。
  - Playwright：新增断言“同一 `series_id` 下 `/api/market/candles` GET 仅 1 次”。
- **怎么回滚**
  - 回退该文件改动（恢复原 catchup 循环）。

### 2) 后端：增加 forming 事件（binance_ws）

- **改什么**
  - `backend/app/ingest_binance_ws.py`：解析 `x=false` 的 kline 更新为 forming。
  - `backend/app/ws_hub.py`：增加 `publish_forming`（或复用现有结构）向订阅者广播 `candle_forming`。
  - `backend/app/main.py`：WS 协议文档化（必要时补充错误码/兼容）。
  - `backend/app/schemas.py`：如需，新增 `CandleForming`（或复用 `CandleClosed` 作为 payload 结构）。
- **怎么验收**
  - 在当前默认运行方式下，WS 能收到 `candle_forming`，且同一 `candle_time` 的 `close/high/low/volume` 会变化。
  - 节流生效：在图表上不会出现“每毫秒刷新”的抖动（或通过日志统计推送频率）。
- **怎么回滚**
  - 保留 `candle_closed` 逻辑不动；撤销新增的 forming 解析与 hub 广播即可。

### 3) 测试/E2E：提供可控的 forming 注入（推荐走 debug API）

Binance 实盘 WS 在 CI/E2E 不稳定，因此建议新增一个仅测试/调试用注入入口：

- **改什么**
  - `POST /api/market/ingest/candle_forming`（只在 `TRADE_CANVAS_ENABLE_DEBUG_API=1` 下可用）：
    - 不写入 SQLite，仅通过 hub 广播 `candle_forming` 给订阅者。
- **怎么验收**
  - Playwright：先 `page.goto(/live)` 建立 WS，再调用该 debug API，断言前端 `data-last-close` 发生变化且 `data-last-time` 不变。
- **怎么回滚**
  - 移除该 debug API（forming 本身仍可保留供真实 ingest 使用）。

---

## 风险与回滚

- **风险：forming 推送频率过高导致前端性能问题**
  - 缓解：服务端节流 + 前端可选 `requestAnimationFrame` 合并更新。
  - 回滚：关闭 forming 推送（env 开关或移除 forming publish）。
- **风险：ccxt 模式下无法提供 forming**
  - 缓解：明确降级策略（只在闭合时更新），不影响主链路。
- **风险：WS catchup 与 HTTP 初始数据重复**
  - 缓解：客户端按 `candle_time` 幂等合并（现有 `mergeCandle` 即可）。

---

## 验收标准

1) 进入某 `series_id`：
   - 正常路径只发生 1 次 `/api/market/candles?limit=2000` HTTP 请求。
   - WS 连接建立并 subscribe 成功。
2) forming 可用（binance_ws 或 debug 注入）时：
   - 最后一根未收线 K 的 OHLC（至少 close/volume）在同一 `candle_time` 下发生变化（图表跳动）。
3) closed 仍为权威：
   - 当收线后（收到 `candle_closed`），对应 `candle_time` 的 forming 被覆盖，且该 K 进入 SQLite（可通过再次 HTTP 查询验证）。

---

## E2E 用户故事（门禁）

## E2E 用户故事（必须覆盖主流程）

### Story ID / E2E Test Case（必须）
- Story ID（建议：`YYYY-MM-DD/<topic>/<short-scenario>`）：`2026-02-02/market/forming-kline-live`
- 关联 Plan：`docs/plan/2026-02-02-market-forming-kline-ws-v1.md`
- E2E 测试用例（必须写到具体文件 + 测试名）：
  - Test file path: `frontend/e2e/market_kline_sync.spec.ts`
  - Test name(s): `live chart loads history once and forming candle jumps`
  - Runner（pytest/playwright/…）：Playwright

### Persona / Goal
- Persona：交易员/研究员在 Live 模式看盘
- Goal：打开某 `series_id` 后一次加载历史；同时看到最后一根未收线 K 线跳动；收线后落库且前端以 closed 覆盖 forming

### Entry / Exit（明确入口与出口）
- Entry（触发方式/输入）：打开 `GET /live`（前端默认 `series_id=binance:futures:BTC/USDT:1m`）
- Exit（成功的可观测结果）：
  - UI：`data-last-time==180` 且 `data-last-close` 在 forming 注入时变化、在 closed 注入后固定为 closed 值
  - HTTP：页面侧仅 1 次 `GET /api/market/candles?limit=2000`
  - DB：`candles` 表包含 `candle_time=180` 的一行（closed 落库）

### Concrete Scenario（必须：写“具体数值”，禁止空泛）

- Chart / Symbol:
  - series_id / pair / timeframe: `binance:futures:BTC/USDT:1m`
  - timezone: UTC（以 `candle_time` Unix seconds 为准）
- Initial State（明确数据前置）：
  - DB empty?: yes（E2E 脚本启动时清空 `backend/data/market_e2e.db`）
  - Existing candles (at least 1) (exact values):
    - candle_time=60 o=1 h=2 l=0.5 c=1.5 v=10
    - candle_time=120 o=1 h=2 l=0.5 c=1.5 v=10
- Trigger Event（明确触发点 + 时间）：
  - forming updates (same candle_time): `candle_time=180`, close changes `10 -> 11 -> 12`（其他字段固定）
  - finalized candle arrives: `candle_time=180` closed with `close=13`
- Expected UI / API observable outcome（写具体）：
  - UI: after forming injections `data-last-time==180` and `data-last-close` becomes `10/11/12`; after closed injection `data-last-close==13`
  - WS: receives `candle_forming` with `candle_time==180`
  - HTTP: page triggers exactly 1 GET to `/api/market/candles` for the history snapshot

### Preconditions（前置条件）
- 数据前置（fixtures / 环境变量 / 数据库初始状态）：
  - `TRADE_CANVAS_ENABLE_WHITELIST_INGEST=0`
  - `TRADE_CANVAS_ENABLE_ONDEMAND_INGEST=0`
  - `TRADE_CANVAS_ENABLE_DEBUG_API=1`（使 E2E 可注入 forming）
- 依赖服务：需要启动 backend + frontend（由 `bash scripts/e2e_acceptance.sh` 启动）

### Main Flow（主流程步骤 + 断言）

1) Step: Seed closed candles into store
   - User action: none（测试前置）
   - Requests:
     - `POST /api/market/ingest/candle_closed` * 2（candle_time=60,120）
   - Backend chain: handler → `store.upsert_closed` → `hub.publish_closed`
   - Assertions:
     - responses are 200
   - Evidence（文件/输出片段/查询）:
     - Playwright test assertion + E2E output

2) Step: Open live chart and load history exactly once
   - User action: open `/live`
   - Requests:
     - `GET /api/market/candles?series_id=...&limit=2000` exactly once
     - `WS /ws/market` + `subscribe { since: 120 }`
   - Backend chain: `get_market_candles` → `store.get_closed` / `store.head_time`; websocket `subscribe` catchup
   - Assertions:
     - candle GET count == 1
     - UI chart area visible
   - Evidence（文件/输出片段/查询）:
     - Playwright request counter + expect

3) Step: Inject forming updates and observe last candle jumps
   - User action: none（测试通过 debug API 注入）
   - Requests:
     - `POST /api/market/ingest/candle_forming` (debug) * 3（candle_time=180, close=10/11/12）
   - Backend chain: debug handler → `hub.publish_forming`
   - Assertions:
     - UI `data-last-time == "180"`
     - UI `data-last-close` changes to `"10"`, `"11"`, `"12"`（至少验证最终变为 `"12"`，并且期间发生过变化）
   - Evidence（文件/输出片段/查询）:
     - Playwright `expect.poll` on `data-last-close`

4) Step: Inject closed candle and ensure closed overrides forming + persists
   - User action: none（测试注入）
   - Requests:
     - `POST /api/market/ingest/candle_closed`（candle_time=180 close=13）
     - (optional) `GET /api/market/candles?since=120&limit=10`（用于确认 DB 返回 180）
   - Backend chain: handler → store upsert → hub publish_closed
   - Assertions:
     - UI `data-last-close == "13"`
     - API returns candle_time==180 in candles array
   - Evidence（文件/输出片段/查询）:
     - Playwright response JSON assertions

### Produced Data（产生的数据）

- Tables / Files:
  - `backend/data/market_e2e.db` (SQLite)
    - table: `candles`
    - keys/fields: `(series_id, candle_time)` primary key; `open/high/low/close/volume`
    - how to inspect: `sqlite3 backend/data/market_e2e.db "select series_id,candle_time,close from candles order by candle_time;"`

### Verification Commands（必须可复制运行）

- Command: `bash scripts/e2e_acceptance.sh`
  - Expected：Playwright 全绿；并在 `output/playwright/` 产出 report（失败时含 trace/video/screenshot）

### Rollback（回滚）
- 最短回滚方式：回退本次修改的前端 `ChartView`、后端 `ws_hub`/`ingest_binance_ws`/debug API 相关变更；forming 功能可通过移除 `candle_forming` 分支或不开启 debug env 来禁用

---

## 变更记录

- 2026-02-02: 创建（草稿）
