---
title: 因子引擎 v1（拓扑依赖 + 冷热真源账本 + delta 二级账本）
status: deprecated
owner:
created: 2026-02-02
updated: 2026-02-09
---

## 背景

trade_canvas 当前已经跑通 v0 主链路（closed candle → pivot/pen 事件落库 → 前端增量 overlay），但“老系统 factor2”里最关键的三件事还缺少一个 **更干净、更简洁、可演进** 的统一设计：

1) **因子拓扑依赖（DAG）**：`pen` 消费 `pivot`，`zhongshu` 消费 `pen`，后续还会出现更复杂的依赖闭包与多实例因子。
2) **冷热两个真源账本**：二者均 append-only，但职责不同：
   - 冷（history）：事件驱动 + 定点切片（纯过滤），避免未来函数
   - 热（head）：局部热快照 + 定点查询（点查 / floor），避免每次切片都短窗重算
3) **delta 二级账本**：把“绘图/指标/策略信号”的增量统一同源化，让 replay / live / overlay / freqtrade 消费口径一致，避免多处重算漂移。

参考来源（批判性继承不变量，不复刻实现负债）：
- `../trade_system/user_data/doc/Core/核心类 2.1.md`
- `../trade_system/user_data/doc/Core/术语与坐标系（idx-time-offset）.md`
- `../trade_system/user_data/doc/Core/Contracts/factor_ledger_v1.md`
- `../trade_system/user_data/doc/Core/Contracts/slot_delta_ledger_v1.md`

本仓真源契约（从这里开始看）：
- `docs/core/contracts/factor_v1.md`
- `docs/core/contracts/factor_graph_v1.md`
- `docs/core/contracts/factor_ledger_v1.md`
- `docs/core/contracts/delta_ledger_v1.md`
- `docs/core/contracts/overlay_v1.md`
- `docs/core/contracts/strategy_v1.md`

## 目标 / 非目标

### 目标（Do）
- 把“闭合K → 因子计算（DAG）→ 事件产出 → 数据落库（冷热）→ 指标产出 → freqtrade 消费开仓（dry-run）”收敛为一条可复现主链路。
- 所有下游只消费同源 ledger/delta（读写分离），缺失时返回 `ledger_missing/build_required`，禁止读路径隐式写入或全量重算。
- 任何时刻 `t` 的 slice 必须满足：`seed ≡ incremental`、history 纯切片、head 无未来函数。
- 具备一条“能失败的”fail-safe：`candle_id` 不一致时必须拒绝信号/拒绝 delta 输出。

### 非目标（Don’t / v1 不做）
- 不一次性复刻 trade_system 的 file ledger + compaction（先用 SQLite 落地语义；后续可迁移）。
- 不引入 replay-package/explain/query-view 的完整协议（先把 delta ledger 同源化）。
- 不引入 forming 进入因子引擎（forming 只用于蜡烛展示）。

## 方案对比（选最优且可落地）

### 方案 A：直接上 trade_system 级 file-ledger（FactorLedger + SlotDeltaLedger）
- 优点：终局形态、天然支持 compaction/index/window/replay。
- 缺点：实现/调度/锁/索引复杂度高；对 trade_canvas 当前“小步可回滚”不友好。

### 方案 B（推荐）：SQLite 语义落地（冷热 ledger + delta ledger），逐步演进到 file-ledger
- 优点：实现最短闭环、测试最容易、易回滚；对 v1 的“语义正确”最友好。
- 缺点：长期需要迁移到 file-ledger/compaction（但可由迁移脚本离线完成，不影响契约）。

### 方案 C：全部靠在线计算（无真源 ledger）
- 优点：代码少。
- 缺点：无法保证可复现；replay/live/overlay/策略必漂移；与项目成功标准冲突。

结论：采用方案 B，先把 **契约与不变量锁死**，再逐步替换存储实现。

## 架构总览（clean + 可插拔）

单一权威输入：`CandleClosed`（见 `market-kline-sync`）

```
CandleClosed (ingest)
  → CandleStore (closed truth)
  → FactorEngineV1 (FactorGraph topo order)
      → ColdLedger (history events, slice)
      → HotLedger  (head snapshots, point query)
      → DeltaLedger (overlay/indicators/strategy outputs, poll/window)
  → Adapters
      → Chart API/WS (delta → frontend)
      → Freqtrade Adapter (delta/ledger → dataframe signals)
```

关键边界：
- 因子实现只关心：`apply_closed()`、`slice_history()`（纯切片）、`get_head()`（点查或短窗重算），以及声明 `depends_on`。
- 读路径只读 ledger；写入只在 ingest/新增 candle 消费路径发生。

## 数据与契约（v1 真源）

- 因子外壳：`FactorSliceV1`（history/head/meta）见 `docs/core/contracts/factor_v1.md`
- 因子拓扑：DAG + 稳定拓扑序 + deps_snapshot 只读，见 `docs/core/contracts/factor_graph_v1.md`
- 冷热 ledger：见 `docs/core/contracts/factor_ledger_v1.md`
- delta 二级账本：见 `docs/core/contracts/delta_ledger_v1.md`

建议的 v1 因子闭包（最小可验收）：
- `pivot`：history=major（confirmed/delayed），head=minor（短窗/可选落 hot）
- `pen`：history=confirmed（delayed），head=last/extending（短窗/可选落 hot）
- `zhongshu`：history=dead（append-only），head=alive（0/1，短窗/可选落 hot）

## 里程碑（小步可回滚）

- M0：引入 FactorGraphV1（DAG 校验 + 稳定拓扑序）与统一调度入口（单点 orchestrator）
- M1：补齐 HotLedger（head 快照 append-only + floor 点查），并把 `pen/zhongshu` 的 head 从“即时计算”迁入 hot
- M2：引入 DeltaLedger（poll/window），把 overlay + 指标点 + 策略信号同源化输出
- M3：freqtrade adapter 消费 delta/ledger（dry-run），并补齐 fail-safe 门禁

## 任务拆解（每步：改什么 / 验收 / 回滚）

- [ ] M0：FactorGraphV1 落地到代码
  - 改什么：新增 `trade_canvas/factor_graph.py`（或等价模块）；后端 orchestrator 改为按 topo 顺序调用因子
  - 怎么验收：新增 `backend/tests/test_factor_graph_cycle_guard.py`（cycle 必失败 + 错误可定位）
  - 怎么回滚：只回滚新模块与 orchestrator 入口，不触及现有 v0 pivot/pen API

- [ ] M1：HotLedger（append-only head snapshots）
  - 改什么：新增 SQLite 表与读写；`/api/factor/slices` 优先点查 head
  - 怎么验收：`seed ≡ incremental` 对拍（至少对 pivot/pen/zhongshu 的 head 字段）
  - 怎么回滚：保留旧“切片阶段短窗重算 head”作为 fallback（feature flag）

- [ ] M2：DeltaLedger（统一增量源）
  - 改什么：新增 `/api/delta/poll`（以及可选 WS）；前端从 delta 获取 overlay；策略从 delta/ledger 获取指标
  - 怎么验收：cursor 增量幂等（重复 poll 不改变重建结果）
  - 怎么回滚：通过 `git revert` 回退本轮改动；读口始终以 `GET /api/draw/delta` 为唯一绘图增量入口

- [ ] M3：freqtrade dry-run 消费（策略侧门禁）
  - 改什么：`trade_canvas/freqtrade_adapter.py` 改为消费本仓 ledger/delta（而非旁路重算）
  - 怎么验收：`pytest -q` 中新增“candle_id mismatch → enter_long 全 false”的回归保护
  - 怎么回滚：保留旧 SMA cross adapter 作为独立 demo，不影响主链路

## 风险与回滚

### 主要风险
- 语义漂移：若绘图/策略旁路重算而不是读 ledger，会出现“画对了但算错了 / 算对了但链路断了”。
- 存储膨胀：hot/head 逐根存快照会增长（需要后续 compaction/截断策略，但契约不变）。
- 尾部修订：最后一根 candle 的修订需要 `seq` 多版本语义（必须在 contract 与读取端锁死）。

### 回滚策略
- 全链路必须支持通过开关降级：
  - `TRADE_CANVAS_ENABLE_FACTOR_INGEST=0`
  - `TRADE_CANVAS_ENABLE_OVERLAY_INGEST=0`
- API 兼容保留（历史计划，已作废）：曾计划保留 `/api/plot/delta` 作为 overlay 兼容读路径，直到 delta ledger 成熟。
  - 更新（2026-02-05）：`/api/plot/delta` 与 `/api/overlay/delta` 已删除；兼容回滚依赖 `git revert`，不再提供旧读口。

## 验收标准

- 同一份 `CandleClosed` 输入跑两次（新 DB），delta 与 latest ledger 的 `(last_candle_id,关键事件条数)` 一致。
- `pen` 与 `zhongshu` 能稳定消费上游依赖（pivot→pen→zhongshu），并且 history 仅通过事件可见性推进（无未来函数）。
- 任何 `candle_id` 不一致时：
  - delta 输出必须拒绝（ledger_out_of_sync）
  - freqtrade adapter 必须 fail-safe（不出入场信号）

## E2E 用户故事（门禁）

### Story ID / E2E Test Case（必须）
- Story ID：`2026-02-02/factor2/full-chain-pivot-pen-zhongshu-freqtrade-dryrun`
- 关联 Plan：`docs/plan/2026-02-02-factor-engine-graph-ledgers-v1.md`
- E2E 测试用例（文件 + 测试名，v1 规划）：
  - Test file path（Playwright）：`frontend/e2e/factor_full_chain.spec.ts`
  - Test name：`full chain: closed → factors → db → delta → chart`
  - Runner：Playwright（由 `bash scripts/e2e_acceptance.sh` 执行）
  - 辅助链路（pytest）：`backend/tests/test_e2e_user_story_factor_graph_delta_freqtrade.py`

### Persona / Goal
- Persona：策略开发者（要把结构因子接到实盘/回测）
- Goal：同一份 K 线输入能稳定产出 `pivot/pen/zhongshu` 的 ledger + delta，并被 freqtrade adapter 消费产生 dry-run 开仓信号

### Entry / Exit
- Entry：通过 `POST /api/market/ingest/candle_closed` 注入一段闭合 K 线序列（series_id 固定）
- Exit：
  - 后端：`/api/factor/slices(at_time=t)` 同时包含 `pivot/pen/zhongshu`
  - 前端：图表渲染出（至少）pivot markers（并可扩展到 pen/zhongshu）
  - 策略侧（dry-run）：DataFrame 出现一次 `enter_long==1`，且 `candle_id` 对齐门禁通过

### Concrete Scenario（具体数值）

- series_id：`binance:futures:BTC/USDT:1m`
- timezone：UTC
- 初始 DB：empty
- 造数（确定性）：`base=60` 秒，`candle_time = base*(i+1)`
  - 价格序列（用于构造交替 pivot，窗口建议 `window_major=2` 便于短序列可验收）：
    - closes = `[1,2,5,2,1,2,5,2,1,2,5,2,1]`

### Main Flow（步骤 + 断言 + 证据）

1) Ingest closed candles（驱动全链路）
   - Action：Playwright 用 `request.post("/api/market/ingest/candle_closed")` 依次注入上述 candles
   - Assertions：
     - `GET /api/market/candles` 返回最新 `candle_time == 780`
     - 后端冷账本（factor history）至少写入 `pivot.major >= 1`
   - Evidence：
     - Playwright trace：`output/playwright/`（由 e2e_acceptance 生成）

2) 查询因子切片（ledger-only）
   - Action：请求 `GET /api/factor/slices?series_id=...&at_time=780`
   - Assertions（最小）：
     - `pivot.history.major.length >= 1`
     - `pen.history.confirmed.length >= 1`
     - `zhongshu` 至少存在（允许 v1 初期为 head-only，但必须满足 `meta.at_time == 780`）
   - Evidence：
     - Playwright 断言或 pytest 断言通过（退出码 0）

3) 前端展示（增量 overlay）
   - User action：打开 `/live`
   - Assertions：
     - `[data-testid="chart-view"][data-pivot-count] > 0`
   - Evidence：
     - Playwright 截图/trace（`output/playwright/`）

4) freqtrade dry-run 消费（adapter）
   - Action：pytest 跑 `backend/tests/test_e2e_user_story_factor_graph_delta_freqtrade.py`
   - Assertions：
     - DataFrame 包含 `tc_ok` 与至少一个结构指标列（例如 `tc_pen_count` / `tc_zhongshu_alive`）
     - 至少出现一次 `enter_long==1`
     - `candle_id` 对齐：latest ledger 的 `candle_id` == candles 真源最新 `candle_id`

5) fail-safe（能失败的门禁）
   - Action：人为让 candle 真源推进但 ledger 不推进（写一根 candle 但不跑因子/或篡改 ledger）
   - Assertions：
     - adapter 必须返回 `ok=false` 或 `enter_long==0` 全部为 false（拒绝交易）

### Produced Data（产物）

- SQLite（同一 DB）：
  - `candles`（closed 真源）
  - `factor_*`（冷/热 ledger）
  - `plot_*` / `delta_*`（绘图/二级增量）
  - `ledger_latest` 或等价表（策略侧最新 ledger）

### Verification Commands（证据）

- `python3 -m pytest -q`
  - 预期：包含 factor DAG/ledger/delta/freqtrade 的回归保护全部通过
- `E2E_PLAN_DOC="docs/plan/2026-02-02-factor-engine-graph-ledgers-v1.md" bash scripts/e2e_acceptance.sh`
  - 预期：Playwright E2E 通过（退出码 0），并产出 `output/playwright/` 证据

### Rollback（回滚）
- 最短回滚：保持 `TRADE_CANVAS_ENABLE_FACTOR_INGEST=0` 与 `TRADE_CANVAS_ENABLE_OVERLAY_INGEST=0`，恢复到纯 market 链路；代码回滚可用 `git revert`。

## 变更记录
- 2026-02-02: 创建（草稿）
