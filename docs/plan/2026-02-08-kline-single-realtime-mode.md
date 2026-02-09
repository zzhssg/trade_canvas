---
title: K 线单一实时模式收敛（binance_ws）与白名单回退 ondemand
status: 已完成
owner: Codex
created: 2026-02-08
updated: 2026-02-08
---

## 背景

- 当前后端同时存在 `ccxt` 与 `binance_ws` 两套实时 ingest 模式，存在运行时分叉与排障成本。
- 当 `TRADE_CANVAS_ENABLE_WHITELIST_INGEST=0` 且订阅的是白名单币种（例如默认 `binance:futures:BTC/USDT:1m`）时，ondemand 不会启动 job，导致 K 线不更新。

## 目标 / 非目标

### 目标

- 后端实时 ingest 仅保留一种模式：`binance_ws`。
- 白名单 ingest 关闭时，白名单币种订阅自动回退到 ondemand，不再“订阅成功但无实时数据”。
- 前端默认链路下（HTTP tail + WS）能够持续收到 `candle_forming/candle_closed`，K 线可见跳动。

### 非目标

- 不改动 HTTP/WS 对外契约字段（`/api/market/candles`、`/ws/market` 消息结构保持不变）。
- 不重构因子/overlay 产物协议。

## 方案概述

1. `IngestSupervisor` 删除 realtime source 选择分支，统一使用 `run_binance_ws_ingest_loop`。
2. 新增“白名单是否常驻 ingest”状态：仅当 whitelist ingest 开关开启时，白名单系列被视为常驻；否则按 ondemand 路径启动/回收 job。
3. 保留 `ccxt` 代码供历史/兼容测试，但不再作为 realtime 运行路径。
4. 更新运行脚本默认值与文档，明确“单一模式 + 回退行为”。

## 里程碑

- M1（后端逻辑）: 单一 realtime 模式 + whitelist 关闭回退 ondemand。
- M2（回归测试）: 补充 whitelist 回退测试并修正现有测试桩。
- M3（文档与运行）: runbook 与 core 文档同步，门禁通过。

## 任务拆解

- [x] `backend/app/ingest_supervisor.py`
  - 改什么：删除 `TRADE_CANVAS_MARKET_REALTIME_SOURCE` 分支；统一 binance_ws；引入 whitelist 常驻判定。
  - 怎么验收：`pytest -q backend/tests/test_ingest_supervisor_capacity.py backend/tests/test_market_ws_disconnect_releases_ondemand.py`
  - 怎么回滚：`git revert <commit>`
- [x] `backend/tests/test_ingest_supervisor_whitelist_fallback.py`（新增）
  - 改什么：覆盖“whitelist ingest 关闭时，白名单订阅会启动 ondemand job”。
  - 怎么验收：`pytest -q backend/tests/test_ingest_supervisor_whitelist_fallback.py`
  - 怎么回滚：删除新增测试并回退逻辑改动。
- [x] `scripts/dev_backend.sh` + `docs/core/market-kline-sync.md` + `docs/runbook/backend.md`
  - 改什么：更新默认开关说明，移除旧模式描述。
  - 怎么验收：`bash docs/scripts/doc_audit.sh`
  - 怎么回滚：回退文档与脚本单文件。

## 风险与回滚

- 风险：
  - 本地/CI 无法访问 Binance WS 时，ondemand job 可能无实时输入。
  - 旧测试中若硬编码 patch `run_whitelist_ingest_loop`，需同步替换 patch 点。
- 回滚：
  - 代码层面单提交可回退：`git revert <sha>`。
  - 运行层面可临时依赖手动 ingest API 验证图表链路（不依赖实时源）。

## 验收标准

- 后端 realtime 路径只有 `binance_ws`。
- 在 `TRADE_CANVAS_ENABLE_WHITELIST_INGEST=0` 时订阅 `binance:futures:BTC/USDT:1m`，`/api/market/debug/ingest_state` 可见该 series job 被启动（source=binance_ws）。
- WebSocket 订阅可收到 `candle_forming` 或 `candle_closed`（任一即可证明“跳动”链路畅通）。

## E2E 用户故事（门禁）

### Story ID / E2E Test Case（必须）

- Story ID（建议：`YYYY-MM-DD/<topic>/<short-scenario>`）：`2026-02-08/kline-single-mode/whitelist-fallback-live`
- 关联 Plan：`docs/plan/2026-02-08-kline-single-realtime-mode.md`
- E2E 测试用例（必须写到具体文件 + 测试名）：
  - Test file path: `backend/tests/test_ingest_supervisor_whitelist_fallback.py`
  - Test name(s): `test_whitelist_series_falls_back_to_ondemand_when_whitelist_ingest_disabled`
  - Runner（pytest/playwright/…）：`pytest`

### Persona / Goal

- Persona：交易员（前端默认打开 BTC/USDT 1m）。
- Goal：即使 whitelist ingest 关闭，图表也能收到实时 K 线更新，不再停在旧数据。

### Entry / Exit（明确入口与出口）

- Entry（触发方式/输入）：前端 WS 发送 `{"type":"subscribe","series_id":"binance:futures:BTC/USDT:1m","since":999999}`。
- Exit（成功的可观测结果）：
  - debug ingest state 中 `binance:futures:BTC/USDT:1m` job 存在；
  - source 为 `binance_ws`；
  - WS 收到 `candle_forming` 或 `candle_closed`。

### Concrete Scenario（必须：写“具体数值”，禁止空泛）

- Chart / Symbol:
  - series_id / pair / timeframe: `binance:futures:BTC/USDT:1m`
  - timezone: `UTC`
- Initial State（明确数据前置）：
  - DB empty?: `false`（示例已有 `candle_time=999999`）
  - Existing candles (at least 1) (exact values):
    - candle_time: `999999`
    - o/h/l/c/v: `1.0/2.0/0.5/111.0/10.0`
- Trigger Event（明确触发点 + 时间）：
  - what happened (e.g. finalized candle arrives): 用户订阅后触发 ondemand realtime job（binance_ws）启动。
  - when (wall-clock or synthetic time): `2026-02-08` 本地运行时。
  - new candle expected (exact values):
    - candle_time: `> 999999`（由实时源决定）
    - o/h/l/c/v: 任意有效数字，需满足 `high>=max(open,close)`、`low<=min(open,close)`。
- Expected UI / API observable outcome（写具体）：
  - UI: 图表最后一根 K 的 `time` 会增加或当前 forming 的 `close` 改变。
  - API: `/api/market/debug/ingest_state` 中存在该 job 且 `running=true`。
  - WS: 收到 `candle_forming` 或 `candle_closed`。

### Preconditions（前置条件）

- 数据前置（fixtures / 环境变量 / 数据库初始状态）：
  - `TRADE_CANVAS_ENABLE_WHITELIST_INGEST=0`
  - `TRADE_CANVAS_ENABLE_ONDEMAND_INGEST=1`
- 依赖服务（是否需要启动 backend/frontend；或纯本地测试即可）：
  - 回归测试可纯后端 pytest；
  - 手工 smoke 需要启动 backend（可选启动 frontend）。

### Main Flow（主流程步骤 + 断言）

1) Step:
   - User action: 连接 `/ws/market` 并订阅 `binance:futures:BTC/USDT:1m`。
   - Requests: `WS subscribe` + `GET /api/market/debug/ingest_state`。
   - Backend chain: `ws_market -> ingest_supervisor.subscribe -> _start_job(run_binance_ws_ingest_loop)`。
   - Assertions: debug state 中该 series `refcount>=1`、`source=binance_ws`。
   - Evidence（文件/输出片段/查询）: pytest 断言 + debug state JSON。

2) Step:
   - User action: 等待 WS 推送。
   - Requests: 无新增请求（仅 WS 消息）。
   - Backend chain: `run_binance_ws_ingest_loop -> hub.publish_forming/publish_closed_batch -> ws client`。
   - Assertions: 收到 `type in {"candle_forming","candle_closed","candles_batch"}` 且 `candle_time` 为整数。
   - Evidence（文件/输出片段/查询）: WS 消息抓取输出。

3) Step:
   - User action: 断开 WS。
   - Requests: WS disconnect + `GET /api/market/debug/ingest_state`。
   - Backend chain: `ws_market.finally -> ingest_supervisor.unsubscribe`。
   - Assertions: job `refcount` 下降到 `0`（随后由 reaper 回收）。
   - Evidence（文件/输出片段/查询）: `test_market_ws_disconnect_releases_ondemand.py` 断言。

### Produced Data（产生的数据）

- Tables / Files:
  - name/path: `candles`（sqlite）
  - keys/fields: `series_id`, `candle_time`, `open/high/low/close/volume`
  - how to inspect: `GET /api/market/candles`
  - name/path: `/api/market/debug/ingest_state`
  - keys/fields: `jobs[].series_id`, `jobs[].source`, `jobs[].refcount`
  - how to inspect: curl/pytest TestClient

### Verification Commands（必须可复制运行）

- Command:
  - `pytest -q backend/tests/test_ingest_supervisor_whitelist_fallback.py backend/tests/test_market_ws_disconnect_releases_ondemand.py`
  - Expected（必须是具体断言的摘要，不要只写“pass”）：whitelist 关闭时白名单订阅会启动 job 且 source=binance_ws；断开 WS 后 refcount 回到 0。
- Command:
  - `pytest -q`
  - Expected（必须是具体断言的摘要，不要只写“pass”）：全量后端回归通过，无新回归失败。

### Rollback（回滚）

- 最短回滚方式（删哪些文件/恢复哪些接口/关哪个开关）：`git revert <sha>` 恢复 `ingest_supervisor` 与测试/文档改动；接口协议不变无需额外迁移。

## 变更记录

- 2026-02-08: 创建（开发中）
- 2026-02-08: 完成单一 realtime 模式收敛、白名单回退 ondemand、测试与文档同步。
- 2026-02-08: 清理旧 realtime 轮询代码（删除 `ingest_ccxt` realtime loop），保留 ccxt client helper 供 replay coverage 使用。
