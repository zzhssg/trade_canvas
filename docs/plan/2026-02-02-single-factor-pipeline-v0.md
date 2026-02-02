---
title: 单因子链路打通 v0（闭合K→因子→冷热存储→增量绘图）
status: 已完成
owner:
created: 2026-02-02
updated: 2026-02-02
---

## 背景

现状（trade_canvas）：
- 市场 K 线链路已具备：`CandleClosed` 写入 SQLite（`backend/app/store.py`）+ `WS /ws/market` 推送（`backend/app/ws_hub.py`），并支持白名单常驻 / 非白名单按需 ingest（`backend/app/ingest_supervisor.py`）。
- 前端“因子面板”已有 UI（`frontend/src/parts/FactorPanel.tsx`），但目前 overlay 仍以“前端本地计算”为主，没有后端因子/绘图产物链路与存储（v0 需把“因子→绘图”下沉到后端，保证可复现与事件可见性）。

参考（trade_system，批判性继承术语/不变量）：
- 调研笔记：`docs/经验/2026-02-02-trade-system-factor2-pipeline-notes.md`
- 本仓契约：`docs/core/contracts/factor_v1.md`、`docs/core/contracts/overlay_v1.md`

## 目标 / 非目标

### 目标（Do）
- 打通一条“单因子”的端到端闭环：消费 `CandleClosed` → 增量计算 → 冷热语义落盘 → 对外增量读取（HTTP/WS）→ 前端渲染。
- 只做 **closed candle finalized-only**（与 `market-kline-sync` 对齐），并满足最小不变量：
  - `seed ≡ incremental`（同输入同输出）
  - history append-only + slice_history 纯过滤
  - 时间主键用 `candle_time`（idx 仅窗口内编号）

### 非目标（Don’t / v0 不做）
- 不引入 trade_system 的 SlotDelta/Replay 协议复杂度（先用 `overlay_v1` 最小形态：lines + overlay_events）。
- 不做多因子拓扑依赖闭包（v0 单因子无依赖；v1 再接 `deps_snapshot`）。
- 不做 forming 蜡烛（仍只展示 closed）。

## 方案概述

### 1) 定义 v0 “单因子”选择与产物（改为 Pivot）

v0 改为实现 **旧系统的 Pivot（极值点）算法**，并用其产出最小绘图闭环：
- events（`overlay_v1`）：`pivot.major` + `pivot.minor`（同时做两套窗口）
  - **绘制内容**：极值点（high/low）markers（点标记/箭头/圆点）。
  - **延迟生成**：事件在“确认可见”的时刻才追加（避免未来函数）；事件 payload 中携带 `pivot_time/pivot_price`，用于前端把点画回到 pivot_time 的蜡烛上。

事件建议 payload（v0 最小字段）：
- `pivot_time`（unix seconds）
- `pivot_price`（float）
- `direction`：`"resistance"|"support"`（或 `kind: "high"|"low"`）
- `visible_time`（unix seconds，与 event 的 `candle_time` 一致）

参数（与旧系统对齐）：
- `pivot_window_major`（例如 50）
- `pivot_window_minor`（例如 5）

约束（两套 pivot 都必须满足）：
- 仅输出 confirmed pivot：`visible_time` 到达才追加事件（append-only）。
- `event.candle_time == visible_time`，绘制落点使用 payload 的 `pivot_time`。

### 2) 后端：引入 Plot/Factor 的持久化 Query Store（先用 SQLite）

新增 SQLite 表（append-only + tail-upsert 友好）：
- `plot_line_points(series_id, feature_key, candle_time, value, PRIMARY KEY(...))`
  - 语义：按 `feature_key` 存每根 K 的一个点；同 time 允许 upsert（尾部修订/幂等）。
- `plot_overlay_events(id INTEGER PRIMARY KEY AUTOINCREMENT, series_id, candle_time, kind, candle_id, payload_json)`
  - 建议加 unique：`(series_id, candle_time, kind)`，用 upsert 保证幂等；`id` 作为 cursor。

对外接口（对齐 `docs/core/contracts/overlay_v1.md`）：
- `GET /api/plot/delta?series_id=...&cursor_candle_time=...&cursor_overlay_event_id=...`
  - 返回 `PlotDeltaV1`：`lines`（增量 points）+ `overlay_events`（增量 events）+ `next_cursor`
- （可选）`WS /ws/plot`：订阅后推送 `plot_delta`（减少轮询延迟；但 v0 可先只做 HTTP 增量拉取）

冷热语义（v0 先用“表结构约束 + 写入策略”表达）：
- 冷（history）：`plot_line_points` / `plot_overlay_events` 视为 append-only（允许同 key 尾部 upsert）。
- 热（head）：用 `plot_head_time(series_id)`（max candle_time）作为“产物推进度”；用于 fail-safe 对齐检查。

### 3) 事件驱动：以 CandleClosed 为唯一触发源

写入触发点（v0 建议只挂一处，避免双写）：
- 在 `POST /api/market/ingest/candle_closed` 以及 ingest loops 的批量写入路径之后，统一调用 `PlotOrchestrator.ingest_closed(series_id, candles[])`：
  1) 按时间顺序计算增量（可用查询近窗或内存状态）
  2) 批量 upsert points/events（单事务）
  3) （可选）广播 plot delta（WS）

关键约束：
- 只消费 closed candle（与 `market-kline-sync` 一致）。
- 不允许读路径隐式写入（缺失时返回空增量或 build_required；由显式 ingest 补齐）。

### 4) 前端：从“本地计算”切换到“后端增量产物”

`frontend/src/widgets/ChartView.tsx` 迁移思路：
- 蜡烛仍从 `GET /api/market/candles` + `WS /ws/market` 获取（不动）。
- Pivot 极值点 markers 改为：
  - 初始拉取：`GET /api/plot/delta`（cursor 为空）拿到 tail window 的 points/events
  - 增量跟随：当收到 `candle_closed` 后，以 cursor 拉取一次 plot delta（或订阅 /ws/plot）
- UI 可见性仍复用 `visibleFeatures`（feature_key -> 显示/隐藏），但数据来源改为后端。

## 里程碑

- M0：补齐 PlotStore（SQLite schema + CRUD）+ PlotDelta HTTP API（只读）
- M1：实现 Pivot v0 增量 ingest（旧系统算法：极值点 + 延迟事件）并在 ingest 路径中触发
- M2：前端改为消费 PlotDelta（用事件绘制 Pivot 极值点 markers；保留本地计算作为 fallback）
- M3：补齐最小 E2E 用户故事与门禁（后端 pytest + 前端 Playwright）

## 任务拆解

- [x] M0（PlotStore + API）
  - 改什么：`backend/app/plot_store.py`（新）+ `backend/app/main.py` 增加 `/api/plot/delta`
  - 怎么验收：`python -m pytest backend/tests -q`
  - 怎么回滚：删除 plot 相关文件与 route；不影响 market 链路
- [x] M1（Pivot v0 ingest：极值点 + 延迟事件）
  - 改什么：
    - `backend/app/plot_orchestrator.py`（新）：消费 `CandleClosed` 计算 pivot（major+minor），产出 `pivot.major` / `pivot.minor` events
    - `backend/app/ingest_ccxt.py`、`backend/app/ingest_binance_ws.py`、`backend/app/main.py`：在 closed candle 成功写入 store 后触发 orchestrator（批量/单根都要覆盖）
  - 怎么验收：
    - 新增 `backend/tests/test_plot_pivot_ingest.py`
      - 对拍：`seed(all_candles)` 的输出 == 逐根 `apply_closed()` 的输出（`seed ≡ incremental`）
      - 可见性：事件只在 `visible_time` 到达时出现（延迟生成），且 payload 中 `pivot_time <= visible_time`
      - 幂等：重复 ingest 同一批 candle，不产生重复事件（或能以 unique/upsert 去重）
  - 怎么回滚：通过 env 开关禁用 orchestrator（只保留 schema 与 API）
- [x] M2（前端接入）
  - 改什么：`frontend/src/widgets/ChartView.tsx` 改为 fetch plot delta；将 `pivot.major` events 渲染为 markers（画在 payload 的 `pivot_time` 上），保留 visibleFeatures 控制
  - 怎么验收：`pnpm -C frontend test`（如已有）+ 手工打开页面确认极值点延迟出现且落点正确
  - 怎么回滚：保留旧前端本地计算路径（feature flag）
- [x] M3（E2E 门禁）
  - 改什么：新增/扩展 Playwright 用例，覆盖“首次打开→历史极值点可见→收线后延迟事件出现并回填到正确 candle_time”
  - 怎么验收：Playwright E2E 退出码 0（作为最终门禁）
  - 怎么回滚：先只保留后端测试门禁；E2E 用例可标记为可选/分组执行

## 风险与回滚

### 风险
- “尾部 upsert / 重复 ingest”导致事件重复：需要幂等约束（例如 unique：`(series_id, kind, pivot_time, pivot_price)` 或 `(series_id, candle_time, kind, payload_hash)`）或显式去重。
- “延迟生成”导致前端困惑：需要在 UI 上明确这是“确认后回填的历史点”（事件 candle_time=visible_time，绘制 time=pivot_time）。
- 前端切换数据源后出现“线条闪烁/空白”：需要把 plot delta 的初始拉取与蜡烛数据加载顺序锁死（先 candles，再 overlay）。
- 性能：pivot（major）若每根都扫窗口会慢；v0 可接受，后续可引入增量维护/批处理优化。

### 回滚
- 后端：通过 env 开关禁用 Plot ingest（只保留 market 链路）。
- 前端：保留本地 SMA/ENTRY 计算作为 fallback（feature flag）。

## 验收标准

端到端用户故事（v0）：
1) SQLite 中已有一段 `CandleClosed` 历史（>= 200 根 1m）。
2) 请求 `GET /api/plot/delta`（cursor 空）返回非空 `overlay_events`（包含 `pivot.major`/`pivot.minor`，若历史足够长能确认）。
3) 写入一根新的 `CandleClosed` 后，再次请求增量 cursor：
   - 在满足确认条件时，overlay_events 追加 `pivot.major`/`pivot.minor`（event.candle_time == visible_time）
   - payload 中 `pivot_time/pivot_price` 可用于前端把点画到 pivot_time 的蜡烛上（延迟回填）

### E2E 门禁（必须跑通）

- 用例：`frontend/e2e/market_kline_sync.spec.ts`
- 数据点（可复现）：
  - `series_id = "binance:futures:BTC/USDT:1m"`
  - 默认窗口：`pivot_window_major=50`、`pivot_window_minor=5`
  - 造数：`candle_time = 60 * (i+1)`，共 `130` 根；价格先单调上升后下降形成 hill（确认至少 1 个 major pivot）
- 断言：
  - 前端 `data-pivot-count > 0`（说明已从后端 plot delta 获取并生成 pivot markers）
  - WS 收到新收线后，`data-last-ws-candle-time` 更新为新 candle_time

验证命令：
- 后端/核心：`python3 -m pytest -q`
- 前后端联调 E2E：`bash scripts/e2e_acceptance.sh`

## 变更记录
- 2026-02-02: 创建（草稿）
- 2026-02-02: 验收通过（pytest + Playwright E2E），状态更新为已完成
