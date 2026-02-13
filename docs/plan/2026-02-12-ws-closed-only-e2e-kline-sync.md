---
title: WS closed-only 修复与真实 E2E 收盘门禁
status: 待验收
owner: Codex
created: 2026-02-12
updated: 2026-02-12
---

## 背景

当前 live 链路中，`/api/market/candles` 的自动 tail backfill 在 `to_time=None` 时会把“当前未收盘桶”写进 `candles`（closed store），导致：
- 前端订阅 `since=server_head_time` 后，WS 的 `forming` 与后续 `closed` 可能被游标跳过；
- 在 4h 等长周期上，表现为“K 线不跳动”；
- `market health` 对 `head_time > expected_latest_closed_time` 的异常形态缺少明确暴露。

该问题已经在本地复现：`binance:spot:BTC/USDT:4h` 出现 `head_time=1770854400` 且 `expected_latest_closed_time=1770840000`，订阅后 25 秒无 WS 更新。

## 目标 / 非目标

### 目标
1. 主链路恢复 strict closed-only：closed store 不再写入未收盘 candle。
2. 修复后 WS 在真实价格变动（forming）和收盘（closed）场景下可稳定推动 UI。
3. 补齐自动化门禁：覆盖“真实 E2E WS 价格变动 + 收盘”并给出证据。
4. 引入 kill-switch（默认关闭）支持灰度与快速回滚。

### 非目标
- 不改现有 HTTP/WS endpoint 形态与字段契约。
- 不重构前端图表渲染架构。
- 不引入新的外部行情源。

## 方案概述

- 在 backfill/tail 覆盖路径统一使用“上一个已收盘时间”作为上界（`expected_latest_closed_time`）。
- 为 strict closed-only 行为增加后端开关：`TRADE_CANVAS_ENABLE_STRICT_CLOSED_ONLY=0`（默认关闭，逐步放开）。
- health 增补异常识别：当 `head_time > expected_latest_closed_time` 时明确标记为 ahead_of_closed_window（用于排障可观测）。
- E2E 增加真实 WS 场景：
  - WS 先收到 `candle_forming`（同一 candle_time 可连续价格变动）；
  - 收盘后收到 `candle_closed`，并断言 UI `data-last-ws-candle-time` 与最后 close 更新。
- `MarketQueryService` 保持不改：严格 closed-only 语义收口在 `StoreBackfillService`，避免在 query 层复制时间上界判断逻辑。

## 里程碑

1. M1（后端语义修正）
   - strict closed-only 计算与 flag wiring 完成。
2. M2（回归防护）
   - 补后端单测：`to_time=None` 不得越过 closed 边界。
3. M3（真实 E2E 门禁）
   - 补 Playwright：真实 WS forming + closed 断言，纳入 E2E gate。
4. M4（文档/证据）
   - 更新 core 文档与 plan 状态，交付命令+输出+产物路径。

## 任务拆解

- [x] 修改 `backend/app/market_data/read_services.py`：`to_time=None` 时对齐到 expected latest closed time（受 flag 控制）。
- [x] 修改 `backend/app/runtime_flags.py` + 相关 wiring：新增 `TRADE_CANVAS_ENABLE_STRICT_CLOSED_ONLY`。
- [x] 修改 `backend/app/market_health_service.py`：新增 ahead-of-closed-window 状态原因。
- [x] 新增/修改 `backend/tests/test_market_data_services.py`、`backend/tests/test_backend_architecture_flags.py`：覆盖 strict closed-only 行为与 wiring。
- [x] 修改 `frontend/e2e/market_kline_sync.spec.ts`：新增真实 WS forming + closed 收盘场景断言。
- [x] 更新 `docs/core/architecture.md`、`docs/core/api/v1/http_market.md`（如需）说明开关与 closed-only 语义。

## 风险与回滚

- 风险：部分依赖“当前桶预写入”的历史行为（若存在）会出现数据延后一个桶。
- 控制：开关默认 `0`，先在 E2E/测试环境固定 `1` 验证，再逐步放开。
- 回滚：
  1) 环境变量关闭 `TRADE_CANVAS_ENABLE_STRICT_CLOSED_ONLY=0`；
  2) 必要时 `git revert <commit>` 回退实现。

## 验收标准

1. 后端：`pytest -q` 通过，新增用例能在旧行为下失败、修复后通过。
2. 前端：`cd frontend && npm run build` 通过。
3. E2E：`bash scripts/e2e_acceptance.sh -- --grep "live chart loads history once and forming candle jumps"` 通过。
4. 证据：交付包含命令、关键输出、Playwright 产物路径（`output/playwright/...`）。

## E2E 用户故事（门禁）

### Story ID / E2E Test Case（必须）
- Story ID：`2026-02-12/ws-closed-only/live-forming-closed-sync`
- 关联 Plan：`docs/plan/2026-02-12-ws-closed-only-e2e-kline-sync.md`
- E2E 测试用例：
  - Test file path: `frontend/e2e/market_kline_sync.spec.ts`
  - Test name(s): `live chart loads history once and forming candle jumps`
  - Runner：`playwright`

### Persona / Goal
- Persona：交易研究员（Live 看盘）
- Goal：在图表上看到实时价格跳动（forming）并在收盘后落定（closed）

### Entry / Exit（明确入口与出口）
- Entry：用户打开 `/live`，目标 `series_id=binance:futures:TCFORMXXXX/USDT:15m`
- Exit：图表最后一根 K 线先随 forming 变动，收盘后 last-ws-candle-time 与 close 固化为 closed 值

### Concrete Scenario（必须：写“具体数值”，禁止空泛）

- Chart / Symbol:
  - series_id / pair / timeframe: `binance:futures:<uniqueSymbol>/USDT:15m`
  - timezone: UTC
- Initial State（明确数据前置）：
  - DB empty?: yes（E2E 独立 sqlite）
  - Existing candles:
    - candle_time: `900`, `1800`
    - o/h/l/c/v: `1/1/1/1/10`, `2/2/2/2/10`
- Trigger Event（明确触发点 + 时间）：
  - 先注入 forming：`candle_time=2700`, close 依次 `10 -> 11 -> 12`
  - 再注入 closed：`candle_time=2700`, close=`13`
- Expected UI / API observable outcome（写具体）：
  - UI: `data-last-time=2700` 且 `data-last-close` 按 `10/11/12` 跳动，closed 后为 `13`
  - API: `/api/market/candles?since=1800` 包含 `candle_time=2700`
  - WS: 收到 `candle_forming(candle_time=2700)` 与 `candle_closed(candle_time=2700)`

### Preconditions（前置条件）
- 数据前置：E2E 脚本固定关键开关，且设置 `TRADE_CANVAS_ENABLE_STRICT_CLOSED_ONLY=1`
- 依赖服务：`scripts/e2e_acceptance.sh` 启动 backend/frontend（非复用）

### Main Flow（主流程步骤 + 断言）

1) Step:
   - User action: 打开 `/live`
   - Requests: `GET /api/market/candles?series_id=...&limit=2000`
   - Backend chain: `market_http_routes.get_market_candles -> MarketQueryService -> StoreBackfillService/CandleStore`
   - Assertions: 初始仅 2 根（900/1800）；不出现 `2700` closed 预写入
   - Evidence: Playwright network + 测试断言日志

2) Step:
   - User action: 注入 forming 三次（close 10/11/12）
   - Requests: `POST /api/market/ingest/candle_forming`
   - Backend chain: `market_ingest_service.ingest_candle_forming -> CandleHub.publish_forming -> WS client`
   - Assertions: UI `data-last-close` 依次变更到 10/11/12；`data-last-time=2700`
   - Evidence: Playwright DOM 断言

3) Step:
   - User action: 注入 closed（close 13）
   - Requests: `POST /api/market/ingest/candle_closed`
   - Backend chain: `market_ingest_service.ingest_candle_closed -> ingest_pipeline -> CandleHub.publish_closed`
   - Assertions: WS 收到 `candle_closed@2700`；UI `data-last-ws-candle-time=2700` 且 `data-last-close=13`
   - Evidence: Playwright 断言 + backend 日志摘要

### Produced Data（产生的数据）
- Tables / Files:
  - `candles`（sqlite）
    - keys/fields: `series_id,candle_time,open,high,low,close,volume`
    - how to inspect: `/api/market/candles` 或 sqlite 查询
  - Playwright 产物
    - path: `output/playwright/`
    - how to inspect: html report / trace

### Verification Commands（必须可复制运行）
- `pytest -q backend/tests/test_runtime_flags.py backend/tests/test_market_data_services.py backend/tests/test_market_health_routes.py backend/tests/test_backend_architecture_flags.py`
  - Expected：strict closed-only 与 wiring/health 回归用例通过
- `cd frontend && npm run build`
  - Expected：前端类型与构建通过
- `bash scripts/e2e_acceptance.sh --skip-playwright-install --skip-doc-audit -- --grep "live chart loads history once and forming candle jumps"`
  - Expected：forming 连续变动 + closed 收盘断言通过

### Rollback（回滚）
- 最短回滚方式：
  - 运行时关闭 `TRADE_CANVAS_ENABLE_STRICT_CLOSED_ONLY=0`
  - 或回退本次 commit

## 变更记录
- 2026-02-12: 创建（草稿）
