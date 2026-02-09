---
title: 市场 K 线 Fastpath v2（freqtrade 数据复用 + 批量落库 + 单一实时源）
status: 草稿
owner:
created: 2026-02-02
updated: 2026-02-08
---

## 背景

现状（trade_canvas）：
- 前端通过 `GET /api/market/candles` 拉历史（`CandleStore`/SQLite），再通过 `WS /ws/market` 跟随实时。
- 实时 ingest 已统一到 Binance kline WS；ccxt 仅保留为 replay coverage 的辅助拉取能力（`backend/app/ccxt_client.py`）。

已观测问题：
- ingest 性能慢的主要根因不是网络/交易所限速，而是 **逐根 candle 建连 + commit**（每批 N 根会产生 N 次 SQLite connect/commit）。
- 非白名单首次打开时，为了补齐历史，往往会触发大量 backfill，逐根写入放大了耗时。

trade_system 参考：
- **历史数据**：用 `freqtrade download-data` 落到 `datadir`（feather/parquet/json），后端读取文件 + 缓存，不自己“逐根写库”。
- **实时**：直接连 Binance kline WS 聚合 `current+finalized`，finalized 再进入统一编排（写盘/ingest/广播）。

本方案目标：在不破坏现有 API/前端逻辑的前提下，把 trade_canvas 的市场 K 线链路升级为 **更快、更稳、更易扩展** 的 v2。

## 目标 / 非目标

### 目标（Do）

- **性能**：白名单/按需 ingest 的写入从“逐根 commit”升级为“批量 upsert + 单次 commit”，显著降低延迟。
- **复用**：可选复用 `freqtrade datadir` 作为历史真源/快速 bootstrap，减少 backfill 时间。
- **单一实时源**：实时 ingest 统一为 `Binance kline WS`（finalized + forming）。
- **不破坏前端**：保持 `GET /api/market/candles` + `WS /ws/market` 协议不变（或仅增加可选字段/开关）。
- **可观测**：能看到每个 `series_id` 的 ingest 速率、写库耗时、head_time 推进情况。

### 非目标（Don’t / v2 不做）

- 完整对齐 trade_system 的 factor2 finalized ingest / overlay diff 直返（属于更大范围的产品链路）。
- 多交易所通用 WS（v2 仍优先 Binance；ccxt 不再承担实时 ingest）。
- 复杂“历史修订/epoch 强失效”机制（先保证闭合 K 的顺序与幂等）。

## 方案概述（推荐架构）

### 1) 统一：以 SQLite 作为对外读取的 Query Store（不改前端）

- `GET /api/market/candles`、`store.head_time()` 等都继续读 SQLite（索引查询、分页稳定、不会被大文件 I/O 影响）。
- v2 重点是：**如何更快、更可靠地把历史/实时写进 SQLite**。

### 2) 引入“历史 bootstrap”层（可选，优先复用 freqtrade）

新增一个 `HistoryBootstrapper`（按 `series_id`）：
- 优先从 `freqtrade datadir` 读取 OHLCV（feather/parquet/json）并批量导入 SQLite。
- 若本地 datadir 缺失/不够：触发 `freqtrade download-data`（受限流/去重保护），下载完成后再导入。
- 导入时按 `(series_id, candle_time)` 幂等 upsert，允许重复运行。

这样可以把“首次打开一个新币种”从“ccxt 大量分页回补 + 逐根 commit”变成“本地文件导入（快）+ 少量追尾实时（小）”。

### 3) 实时源（单一）

当前仅保留 **BinanceWsIngestor**：
- 直接订阅 Binance kline WS（spot/futures 不同 endpoint），处理 finalized（`k.x = true`）并写入/广播。
- forming（`k.x = false`）只用于 WS 展示，不落库。
- 历史上的 ccxt PollIngestor 已删除（2026-02-08）。

注意：无论哪种实时源，对外只输出 **closed candle**（与现有契约一致）。

### 4) 与现有 Supervisor/WS 逻辑的衔接

- `IngestSupervisor` 仍负责 whitelist 常驻与 on-demand 订阅计数/idle 回收。
- 但它启动的 job 已统一为 `run_binance_ws_ingest_loop(series_id)`：
  - startup：先 `bootstrap_if_needed(series_id)`
  - live：启动 realtime（poll 或 ws）
  - shutdown：尊重 idle_ttl

## 里程碑

- M0（立刻止血）：批量写库优化（ccxt ingest）
- M1（历史 fastpath）：freqtrade datadir → SQLite bootstrap（可选开关）
- M2（实时 fastpath）：Binance kline WS finalized-only（可选开关，保留轮询兜底）
- M3（观测/运维）：指标、日志、自检 endpoints、限流与去重
- M4（E2E）：补齐后端/前端 E2E 覆盖（含 fastpath 分支）

## 当前状态（2026-02-02）

- [x] M0：完成（批量 upsert + 单次 commit）
- [x] M1：完成（freqtrade feather tail 导入 SQLite，`TRADE_CANVAS_MARKET_HISTORY_SOURCE=freqtrade`）
- [x] M2：完成（Binance kline WS realtime source）
- [x] M3：完成（观测/自检/限流：debug endpoint、on-demand 容量上限、批处理日志）
- [x] M4：完成（FE/BE 联调 Playwright E2E gate 通过）

可用开关：
- `TRADE_CANVAS_MARKET_HISTORY_SOURCE=freqtrade`：空库时尝试从 freqtrade datadir 导入（tail）
- `TRADE_CANVAS_FREQTRADE_DATADIR=/abs/path/to/user_data/data/binance`：显式指定 datadir（优先于 config 推导）
- realtime ingest 无二选一开关：默认且唯一为 Binance kline WS
- `TRADE_CANVAS_ONDEMAND_MAX_JOBS=<n>`：非白名单按需 ingest 的最大并发 job 数（满了会优先驱逐 idle job；否则 WS 会收到 `error code=capacity`，订阅失败且不会推送 catchup/stream）
- `TRADE_CANVAS_ENABLE_DEBUG_API=1`：开启 `GET /api/market/debug/ingest_state`
- `TRADE_CANVAS_BINANCE_WS_BATCH_MAX=<n>` / `TRADE_CANVAS_BINANCE_WS_FLUSH_S=<seconds>`：Binance WS ingest 的批量落库阈值

E2E 证据（2026-02-02）：
- `bash .codex/skills/tc-market-kline-fastpath-v2/scripts/verify_fastpath_v2.sh`（exit 0）
- `bash scripts/e2e_acceptance.sh`（exit 0）
- Playwright 产物：`output/playwright/.last-run.json`

## 任务拆解（每步：改什么 / 怎么验收 / 怎么回滚）

### M0：ccxt 批量写库（历史里程碑，已清理 realtime 入口）

- 改什么：
  - 历史上在 `backend/app/ingest_ccxt.py` 完成过批量写库优化；当前 realtime loop 已删除，ccxt helper 位于 `backend/app/ccxt_client.py`。
  - `backend/app/store.py` 的批量 upsert 能力仍被 realtime/replay 复用。
- 怎么验收：
  - `python -m pytest backend/tests/test_ingest_ccxt_symbol.py -q`
  - `python -m pytest backend/tests/test_ingest_ccxt_timeout_option.py -q`
  - `python -m pytest backend/tests/test_e2e_user_story_market_sync.py -q`
- 怎么回滚：
  - revert `backend/app/ccxt_client.py` 与 replay coverage 相关改动，不影响 realtime 主链路。

### M1：freqtrade datadir → SQLite bootstrap（建议）

- 改什么：
  - 新增：`backend/app/history_bootstrapper.py`（或 `backend/app/market_history.py`）
  - 新增：解析 `series_id` → (pair, candle_type/market_mode, timeframe) → datadir 文件路径的映射逻辑（参考 trade_system 的命名规则）。
  - `backend/app/main.py` / `backend/app/ingest_supervisor.py`：on-demand subscribe 或 whitelist start 时，优先调用 `bootstrap_if_needed(series_id, min_candles=...)`。
  - 新增 env：
    - `TRADE_CANVAS_MARKET_HISTORY_SOURCE=freqtrade|ccxt|off`（默认 off，不改变现状）
    - `TRADE_CANVAS_FREQTRADE_DATADIR=...`（可从 `TRADE_CANVAS_FREQTRADE_CONFIG` 的 `datadir` 推导）
- 怎么验收：
  - 新增后端测试：`backend/tests/test_market_history_bootstrap.py`
    - 给定一个小的样例数据文件（fixture），启动 bootstrap 后：
      - `GET /api/market/candles?limit=2000` 返回非空
      - SQLite `candles` 行数增长
  - 不中断现有测试：`python -m pytest backend/tests -q`
- 怎么回滚：
  - 关闭 `TRADE_CANVAS_MARKET_HISTORY_SOURCE`（或删除 bootstrap 调用点），保留文件但不启用。

### M2：Binance kline WS realtime（推荐）

- 改什么：
  - 新增：`backend/app/ingest_binance_ws.py`（仅 Binance；spot/futures 两套 URL）
  - `IngestSupervisor` 统一调用 `run_binance_ws_ingest_loop`（单一 realtime 模式）
  - 与 `CandleHub`/`WS /ws/market` 的 `gap` 逻辑保持一致（按 timeframe 推进）。
- 怎么验收：
  - 单元测试：解析 payload + URL 拼接（可纯本地，不连网）。
  - 集成测试（可跳过外网）：通过 `POST /api/market/ingest/candle_closed` 模拟 finalized 写入，验证 WS 推送与 HTTP 增量读取（复用现有 `test_market_ws.py`/`test_market_e2e_frontend_contract.py`）。
- 怎么回滚：
  - revert `ingest_supervisor` + `ingest_binance_ws` 改动；保持对外 HTTP/WS 契约不变。

### M3：观测与限流（建议）

- 改什么：
  - 关键日志：每次 ingest 批处理记录 `series_id / rows / db_ms / publish_ms / head_time`。
  - （可选）新增 `GET /api/market/debug/ingest_state`：活跃 job、refcount、last_head_time、来源类型。
  - 对 `freqtrade download-data` 加“去重 + 冷却窗口”，避免被刷爆。
- 怎么验收：
  - `python -m pytest backend/tests -q`
  - 人工验证：打开非白名单重复切换时，不会触发 download-data 风暴（日志可见）。
- 怎么回滚：
  - 关闭 debug endpoint 或将其挂到 debug env 开关。

### M4：E2E 覆盖（必须）

- 改什么：
  - 后端：补充一个覆盖 fastpath 的测试（bootstrap + HTTP + WS）。
  - 前端：复用现有 `frontend/e2e/market_kline_sync.spec.ts`，新增断言：首次请求后 `candles.length > 0` 且 WS 收到 `candle_closed` 后图表不空白。
- 怎么验收：
  - `python -m pytest backend/tests/test_e2e_user_story_market_sync.py -q`
  - `pnpm -C frontend test:e2e frontend/e2e/market_kline_sync.spec.ts`
- 怎么回滚：
  - 若 fastpath 分支暂缓，保留现有 E2E；新增的 fastpath 测试用 env 进行条件启用。

## 风险与回滚

### 风险

- 引入 freqtrade/pyarrow 依赖导致部署复杂度上升（需明确：fastpath 可选开关，默认不启用）。
- datadir 命名/市场模式（spot/futures、`:USDT`）映射错误导致读不到数据（需要严格的映射与 fallback）。
- 引入 Binance WS 需要网络稳定与重连策略（通过重连与 gap 补齐保障，不再依赖 ccxt 轮询兜底）。

### 回滚

- 全量回滚到 v1：只保留 M0 的批量写库优化（对外契约不变）。
- fastpath 通过 env 开关控制：`HISTORY_SOURCE=off`（realtime 始终走 Binance WS）。

## 验收标准

- 性能：
  - 在 backfill 场景下，SQLite commit 次数≈批次数（不再与 candle 数线性相关）。
  - 首次打开非白名单时，历史数据可在“可接受时间”内可用（具体阈值由后续基准测试给出）。
- 正确性：
  - `candles` 始终按 `candle_time` 升序输出；幂等 upsert 不产生乱序/重复（客户端去重后单调）。
  - `WS candle_closed` 与 `HTTP since` 的增量结果一致；gap 时客户端能自动补齐恢复。

## E2E 用户故事（必须覆盖主流程）

### Persona / Goal
- Persona：交易员/策略开发者（打开任意币对的 K 线图）
- Goal：首次打开能快速看到历史 K 线，并能持续收到闭合 K 的更新

### Entry / Exit（明确入口与出口）
- Entry（触发方式/输入）：前端打开某 `series_id`（或直接调用 `GET /api/market/candles` + `WS subscribe`）
- Exit（成功的可观测结果）：
  - `GET /api/market/candles` 返回非空 candles + 合理的 `server_head_time`
  - `WS /ws/market` 收到 `candle_closed` 后，前端图表不空白且 candle 追加/更新

### Preconditions（前置条件）
- 数据前置：准备一个样例 `freqtrade datadir` OHLCV 文件（fixture），覆盖至少 2100 根 1m candle。
- 依赖服务：
  - backend：FastAPI（测试内用 TestClient 即可）
  - frontend：Playwright E2E（可选，作为最终门禁）

### Main Flow（主流程步骤 + 断言）

1) Step: 历史 bootstrap + HTTP 读取
   - Action: 在 SQLite 为空的情况下请求 `GET /api/market/candles?series_id=...&limit=2000`
   - Assertions:
     - 返回 200，`candles.length == 2000`
     - `server_head_time == candles[-1].candle_time`
     - SQLite 中该 `series_id` 的行数 > 0（证明 bootstrap/import 生效）
   - Evidence: `backend/tests/test_market_history_bootstrap.py` 断言 + 临时 db 路径

2) Step: WS 订阅 + 推送一致性
   - Action: 连接 `WS /ws/market` subscribe；通过 `POST /api/market/ingest/candle_closed` 写入 next candle（模拟 finalized）
   - Assertions:
     - WS 收到 `candle_closed`，其 `candle_time` 为 next
     - `GET /api/market/candles?since=<last>&limit=5000` 返回包含该 next candle
   - Evidence: 复用/扩展 `backend/tests/test_market_ws.py`

3) Step: 前端不空白（最终门禁）
   - Action: Playwright 打开页面，等待首次 candles 拉取完成，再触发一次写入并等待 UI 更新
   - Assertions:
     - 页面无空白（canvas 不黑屏/无 error toast）
     - 网络层观察到 `/api/market/candles` 200 且随后 WS message 到达
   - Evidence: `frontend/e2e/market_kline_sync.spec.ts`（trace/screenshot）

### Produced Data（产生的数据）

- Tables / Files:
  - `backend/data/market.db`（或测试用临时 db）
    - keys/fields: `candles(series_id, candle_time, open, high, low, close, volume)`
    - how to inspect: `sqlite3 <db> "select count(*) from candles where series_id=...;"`
  - （可选）`freqtrade datadir` OHLCV 文件（feather/parquet/json）
    - keys/fields: `date/open/high/low/close/volume`

### Verification Commands（必须可复制运行）

- Command: `python -m pytest backend/tests/test_e2e_user_story_market_sync.py -q`
  - Expected: exit code 0
- Command: `pnpm -C frontend test:e2e frontend/e2e/market_kline_sync.spec.ts`
  - Expected: exit code 0（产生 playwright trace）

### Rollback（回滚）
- 最短回滚方式：关闭 fastpath history env（`TRADE_CANVAS_MARKET_HISTORY_SOURCE=off`），并 revert realtime 改动提交，保留对外契约不变。

## 变更记录
- 2026-02-02: 创建（草稿）
