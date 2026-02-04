---
title: Overlay Delta v0（instruction_catalog_patch + active_ids，统一绘图指令底座）
status: in_progress
owner:
created: 2026-02-02
updated: 2026-02-04
---

## 背景

当前问题（需要收敛架构）：
- 前端同时消费 `plot_delta`（pivot markers）与 `factor_slices`（pen polyline），在前端做“状态机/拼装”。
- 统一的绘图契约（现以 `docs/core/contracts/draw_delta_v1.md` 为准）与当时实现存在偏差：代码里已出现 `/api/overlay/delta`（instruction catalog patch），但前端与 E2E 仍主要跑 `/api/plot/delta`（overlay events）+ `/api/factor/slices`（pen）。现状（2026-02-04）：`/api/plot/delta` 与 `/api/overlay/delta` 已移除，读口统一收敛到 `/api/draw/delta`。

目标是把“做图”收敛成：**后端产出统一指令 + 落库 + 增量协议**，前端只负责渲染，避免屎山。

## 现状盘点（截至 2026-02-02）

- 后端已具备 v0 基座：
  - `GET /api/draw/delta`（`backend/app/main.py`）
  - `OverlayStore`（`backend/app/overlay_store.py`）+ `OverlayOrchestrator`（`backend/app/overlay_orchestrator.py`）
- 前端仍未接入：`frontend/src/widgets/ChartView.tsx` 仍以 `plot_delta + factor_slices` 拼装。
- Playwright 门禁用例仍断言 “pivot markers 来自 plot delta”（`frontend/e2e/market_kline_sync.spec.ts`）。

## 目标 / 非目标

### 目标（Do）
- 引入统一绘图增量接口：`GET /api/draw/delta`
  - 返回 `instruction_catalog_patch + active_ids + next_cursor`
  - 指令定义为 JSON 友好的 `OverlayInstructionV1`（marker / polyline）
- 后端落库 overlay 指令（SQLite），并支持增量 patch（按 version_id 单调递增）
- 前端只消费 `/api/draw/delta` 来渲染 pivot/pen（不再拼装 plot+factor 两路）

### 非目标（Don’t）
- 不引入 slot-delta/replay 复杂度（v0 先用 active_ids 全量快照 + catalog patch 增量）
- 不做 forming overlay（forming 仍只用于蜡烛展示）

## 方案对比（收敛口径）

### 方案 A：继续用 `plot_delta (events) + factor_slices (snapshots)`（现状）
- 优点：已跑通 v0。
- 缺点：前端拼装/状态机不可控；同源性差；后续 replay/live/策略消费极易漂移。

### 方案 B（推荐）：`overlay/delta`（catalog patch + active_ids）作为绘图唯一真源接口
- 优点：后端“定义/落盘/增量”一体化；前端变成纯渲染；指令可以被 replay / delta ledger 复用。
- 缺点：需要一次性迁移前端与 E2E（但可用 feature flag 回滚）。

### 方案 C：直接上 `delta_ledger_v1` 全量二级账本（一步到位）
- 优点：终局统一。
- 缺点：当前跨度过大，不符合“小步可回滚”；v0 先把 overlay 指令底座收敛出来更稳。

结论：采用方案 B；把 `overlay/delta` 锁死为“统一绘图指令底座”，并把它作为后续 `delta_ledger_v1` 的一个子流（overlay channel）。

## 协议（v0）

### Cursor
- `cursor_version_id`：客户端已合并的最后一个指令版本号（SQLite autoincrement）

### Response
- `to_candle_time`：服务端当前 overlay 对齐的最新收线时间
- `active_ids`：此时刻应该渲染的指令 id（**窗口裁剪**：仅 tail window 内的指令）
- `instruction_catalog_patch`：`version_id > cursor_version_id` 的指令定义增量（同 id 覆盖即 update）

### 指令定义（v0 最小集合，建议锁定字段）

- `marker`（pivot major/minor）
  - `instruction_id`：`pivot.<level>:<pivot_time>:<direction>:<window>`
  - `definition`（示意）：`{ type:"marker", feature:"pivot.major|pivot.minor", time, position, color, shape, text }`
- `polyline`（pen.confirmed）
  - `instruction_id`：`pen.confirmed`
  - `definition`（示意）：`{ type:"polyline", feature:"pen.confirmed", points:[{time,value}...], color, lineWidth }`

### 必须不变量（本次底座的“硬门禁”）

- 单一权威输入：只随 `CandleClosed` 推进（forming 不进 overlay）。
- 游标单调：`version_id` 单调递增；客户端合并 `patch` 幂等。
- 对齐：`to_candle_time` 必须是 CandleStore 中存在的 `closed`；若不对齐必须降级/拒绝输出（fail-safe，避免画错证据）。
- 窗口裁剪：`active_ids` 只表达“当前窗口内需要渲染的指令集合”，不引入删除语义；客户端可据此决定是否卸载图元。

## 存储（SQLite）

新增表（同 `TRADE_CANVAS_DB_PATH`）：
- `overlay_series_state(series_id, head_time, updated_at_ms)`
- `overlay_instruction_versions(version_id, series_id, instruction_id, kind, visible_time, def_json, created_at_ms)`

> v0 允许同一 `instruction_id` 多版本（pen polyline 会更新）；客户端以 patch 覆盖实现“更新语义”。

## 与 `factor-engine-graph-ledgers-v1` 的关系（对齐路线）

- 本 plan 的 `overlay/delta` 先解决“绘图指令底座”的统一（后端落盘 + 增量读 + 前端纯渲染）。
- 后续 `delta_ledger_v1` 里会把 overlay 指令版本流纳入 `DeltaRecordV1.overlay_*`（或等价），实现 replay/live/策略三方同源。
- 因此 v0 的关键是把 `instruction_id/kind/visible_time/version_id` 的语义锁死，避免未来迁移时口径漂移。

## E2E 用户故事（门禁）

### Story ID / E2E Test Case（必须）

- Story ID：`2026-02-02/overlay-delta/v0/live-chart-overlay-from-overlay-delta`
- 关联 Plan：`docs/plan/2026-02-02-overlay-delta-v0.md`
- E2E 测试用例（文件 + 测试名，v0 规划）：
  - Test file path（Playwright）：`frontend/e2e/market_kline_sync.spec.ts`
  - Test name：`live chart loads catchup and follows WS`（将从“plot delta”迁移为“overlay delta”断言）
  - Runner：Playwright（由 `bash scripts/e2e_acceptance.sh` 执行）

### Persona / Goal

- Persona：策略开发者（观察结构因子在 live 图上的证据）
- Goal：同一份 closed K 线输入驱动后端生成绘图指令；前端仅通过 `/api/draw/delta` 渲染出 pivot markers + pen polyline，并能在 WS 收到新收线后增量更新

### Entry / Exit

- Entry：通过 `POST /api/market/ingest/candle_closed` 注入一段闭合 K 线序列（`series_id` 固定）
- Exit：
  - 后端：`GET /api/draw/delta` 返回 `active_ids.length > 0` 且 `instruction_catalog_patch` 可合并复现
  - 前端：`/live` 页面渲染出 `pivot markers > 0`，且 `pen` 折线点数 > 0（窗口内）
  - 增量：再注入 1 根新 closed candle 后，WS 推进 + overlay delta cursor 推进（仍能渲染）

### Concrete Scenario（具体数值）

- series_id：`binance:futures:BTC/USDT:5m`（与现有 Playwright 用例保持一致）
- base：300 秒；总 candles：130（先升后降，确保 major pivot 可见）
- 追加一根：`candle_time = 300*(130+1)`

### Main Flow（步骤 + 断言 + 证据）

1) HTTP 注入一段 K 线（产生 pivot/pen）
   - Assertions：
     - `GET /api/market/candles` 能返回该 series 的 tail candles（>=2）
   - Evidence：Playwright trace（`output/playwright/`）
2) 前端加载 `/live`，拉取 `/api/draw/delta` 并渲染
   - Assertions：
     - `[data-testid="chart-view"][data-pivot-count] > 0`
     - `[data-testid="chart-view"][data-pen-point-count] > 0`
   - Evidence：Playwright trace + screenshot（`output/playwright/`）
3) 再注入一根新 closed candle，前端通过 WS 收到并触发 overlay delta 增量拉取
   - Assertions：
     - `[data-testid="chart-view"][data-last-ws-candle-time] == 300*(130+1)`
     - overlay cursor 单调推进（可通过前端 debug attribute 或后端日志/断言补证）
   - Evidence：Playwright trace（`output/playwright/`）

### fail-safe（能失败的门禁）

- 场景：让 CandleStore 推进到 `t`，但 overlay 未推进（禁用 `TRADE_CANVAS_ENABLE_OVERLAY_INGEST=0` 或人为制造 overlay lag）
- 断言：前端不得展示“对不齐的伪证据”
  - 可接受行为：`/api/draw/delta` 的 `to_candle_time < market.head_time`，或明确返回 `ledger_missing/build_required`
  - 不可接受行为：`to_candle_time` 超过 candle 真源 / 或渲染出与真源不一致的指令

## 里程碑（小步可回滚）

### M1：锁死契约 + 对齐文档（只动文档/类型，不改行为）

- 改什么：
  - 更新 `docs/core/contracts/draw_delta_v1.md`：以 `DrawDeltaV1`（catalog patch）为主契约；`overlay_v1` 标记 deprecated；旧的 `/api/plot/delta`/`/api/overlay/delta` 已移除
  -（可选）在 `docs/core/contracts/delta_ledger_v1.md` 补一句：overlay 指令流将作为 delta 的一个子流接入
- 怎么验收：
  - `bash docs/scripts/doc_audit.sh`
- 怎么回滚：
  - `git revert` 回退对应 doc 改动

### M2：前端接入 overlay/delta（带 feature flag，可回滚）

- 改什么：
  - `frontend/src/widgets/chart/api.ts`：新增 `fetchOverlayDelta()`
  - `frontend/src/widgets/ChartView.tsx`：新增 overlay state（cursor + catalog），从指令渲染 pivot/pen；保留旧链路作为 fallback
  - `frontend/src/widgets/chart/types.ts`（或 openapi types）：补齐 `OverlayDeltaV1` 类型
- 怎么验收：
  - `cd frontend && npm run build`
  - `bash scripts/e2e_acceptance.sh`（此时 E2E 仍可先跑旧断言；下一里程碑再切）
- 怎么回滚：
  - feature flag 关闭（例如 `VITE_USE_OVERLAY_DELTA=0` / 或 query param）
  - 或 `git revert` 回退前端改动

### M3：切换 E2E 门禁到 overlay/delta（证明“唯一真源接口”）

- 改什么：
  - `frontend/e2e/market_kline_sync.spec.ts`：把 “pivot markers 来自 plot delta” 的描述与断言迁移为 overlay delta（仍断言 `data-pivot-count > 0`）
  -（建议）增加 `data-pen-point-count > 0` 断言，证明 pen 也走 overlay 指令
- 怎么验收：
  - `E2E_PLAN_DOC="docs/plan/2026-02-02-overlay-delta-v0.md" bash scripts/e2e_acceptance.sh`
- 怎么回滚：
  - 回退 E2E 改动；或临时切回旧链路 feature flag

### M4：收敛/清理（可选，放到 v0 完成后再做）

- 改什么：
  - 停止在 chart 主路径调用 `/api/plot/delta` 与 `/api/factor/slices`（现状：已收敛为 `/api/draw/delta` + world frame）
  - `PlotStore/PlotOrchestrator` 已于 2026-02-04 移除
- 怎么验收：
  - `pytest -q`
  - `bash scripts/e2e_acceptance.sh`
- 怎么回滚：
  - 重新启用旧链路（feature flag）或 `git revert`

Commands：
- `python3 -m pytest -q`
- `E2E_PLAN_DOC="docs/plan/2026-02-02-overlay-delta-v0.md" bash scripts/e2e_acceptance.sh`

## 变更记录
- 2026-02-02: 创建（开发中）
