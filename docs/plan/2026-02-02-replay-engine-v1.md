---
title: Replay 回放引擎 v1（t 帧输出：因子切片 + 绘图指令；K 线最小化增删）
status: 草稿
owner:
created: 2026-02-02
updated: 2026-02-02
---

## 背景

trade_canvas 的主链路约束是“closed candle 为权威输入”，并要求 replay/live 同口径可复现。
当前仓库已有：
- 市场 K 线真源与对齐口径：`docs/core/market-kline-sync.md`
- 因子切片读口（v0 debug）：`GET /api/factor/slices`
- 绘图增量读口（v1 底座雏形）：`GET /api/draw/delta`

本计划在不破坏既有链路的前提下，设计 replay 引擎的 v1 技术方案：在 **t 时刻** 输出两个产物：
1) 因子数据切片（冷 + 热）
2) 指令绘图（draw delta）

并明确前端播放 K 线时的“最小化增删”策略（避免每一帧全量 setData）。

## 目标 / 非目标

### 目标
- 定义 replay 的 **统一帧输出契约**（对齐点、fail-safe、可复现、cursor 幂等）。
- 给出后端 QueryView 的最小落地路径（复用现有 store/读口形状，增加必要的 `at_time` 上限能力）。
- 给出前端播放（forward/rewind/seek）的最小化增删策略与 apply 规则。
- 给出 1 条可执行的 E2E 用户故事门禁（允许初版先失败在“正确的缺失点”）。

### 非目标（本计划不做）
- 不在本计划内一次性实现完整 replay UI、完整 delta ledger、完整 forming head。
- 不把 forming 引入因子真源账本与策略口径（forming 仅用于显示）。
- 不为追求“快出画面”而让策略绕过 ledger / 重新计算因子（见 `docs/复盘/2026-02-02-freqtrade-strategy-bypasses-ledger.md`）。

## 方案概述

### 方案 A（推荐）：Replay QueryView = “t 帧投影器”

核心思想：后端提供一个 QueryView，给定 `series_id + at_time + cursors`，产出 `ReplayFrameV1`：
- `factor_slices`：基于因子真源账本的纯切片（冷+热）
- `draw_delta`：基于 overlay/draw 的 cursor 增量，但 **上限必须是 aligned_time**

契约真源：`docs/core/contracts/replay_frame_v1.md`

优点：
- 最小改动即可把“t 帧”形状固定下来，便于前后端对齐与回放验收。
- replay/live 可逐步收敛到 delta ledger（`delta_ledger_v1`）而不推翻 UI apply 引擎。

代价：
- 初期可能仍需从 store 进行“窗口切片查询”，性能需要后续通过索引/缓存优化（但不牺牲契约正确性）。

### 方案 B（后续）：直接以 delta ledger 作为 replay 真源

核心思想：后端先构建 `DeltaRecordV1`（`delta_ledger_v1`），replay 只按 cursor 消费 delta 并重建帧状态。

优点：回放与实盘完全同源；读放大最小。
代价：实现面更大，需要先补齐 delta ledger 的写入与一致性门禁。

结论：v1 先做方案 A，把“帧契约 + 对齐门禁 + apply 规则”钉死，再逐步把数据源下沉到 delta ledger（方案 B）。

## 关键设计点（v1）

### 1) t 的定义与对齐

- replay 的 `t` 只能落在闭合 K（`aligned_time = floor_time(series_id, at_time)`）。
- `candle_id = "{series_id}:{aligned_time}"`
- 所有输出必须对齐到同一个 `candle_id`，否则 fail-safe（`ledger_out_of_sync`）。

### 2) 因子切片（冷+热）

- 冷（cold/history）：`<=t` 的 append-only 事件切片（纯过滤语义，禁止隐式重算）。
- 热（hot/head）：`<=t` 的快照/视图（允许表达尾部中间态/预览，但不得污染 cold，策略默认不读它）。
- 输出形状：复用 `GetFactorSlicesResponseV1`（现有 `/api/factor/slices`）。

### 3) 绘图指令（draw delta）

Draw delta 的 replay 关键点是：它必须支持 **“按 t 上限”** 的增量投影：
- `draw_delta.to_candle_time == aligned_time`
- `instruction_catalog_patch`：`visible_time <= aligned_time` 且 `version_id > cursor`
- `active_ids`：只包含 tail window 内激活的指令（窗口以 `aligned_time` 为右边界）

现状：`/api/draw/delta` 当前上限默认为 store/overlay head（偏 live）。
v1 落地建议：新增 `at_time` 或 `to_time` query，用于 replay 的上限控制（不改变默认行为，便于回滚）。

### 4) K 线播放“最小化增删”（前端 apply 规则）

目标：避免“每一帧 setData 全量重设”，把数据写入成本压到：
- forward：`update`（追加/更新末尾）
- jump/rewind：一次性 `setData` rebase

规则（推荐实现）：
- Step forward（相邻 +1 根）：
  - 若新 bar 的 `time` == 当前最后一根：`update(last)`（尾部修订/重放）
  - 若 `time` > 当前最后一根：`update(new)`（追加）
- Step backward / seek（非相邻跳转）：
  - 对“目标 t 的窗口”（例如最近 2000 根）执行 `setData(window)`（rebase）
- 窗口裁剪（避免无限增长）：
  - 当本地缓存 bars 超过阈值（如 5000）时，仅在下一次 seek 或显式触发时 rebase 到最近 N 根；
  - 不在每帧执行“删除头部”（lightweight-charts 不擅长频繁删头）。

## 里程碑

1) 契约落盘（文档）：`ReplayFrameV1`（done = 评审通过，可对齐实现）。
2) 后端 QueryView 最小实现（可选开关）：`GET /api/replay/frame?series_id&at_time&cursors...`。
3) 前端 replay player（可选开关）：能逐根播放 candles + apply draw delta，并展示 factor slices（调试面板即可）。
4) 回归门禁：固定 fixtures 的“同输入同输出”对拍 + fail-safe out-of-sync。

## 任务拆解

- [ ] 新增契约：`docs/core/contracts/replay_frame_v1.md`（已落盘）
- [ ] 后端：为 draw delta 增加 `at_time/to_time` 上限参数（保持默认不变）
- [ ] 后端：新增 `replay_query_view`（把 factor_slices + draw_delta 组合成 `ReplayFrameV1`）
- [ ] 前端：新增 replay player apply 引擎（bars 最小化增删 + draw delta 幂等 apply）
- [ ] 测试：新增 replay 帧门禁测试（对齐/幂等/可复现）

## 风险与回滚

### 风险
- 对齐漂移：draw/factor/market 任何一个链路未对齐到同一 `candle_id`，会出现“画对了但算错了”。
- 性能：回放逐帧 slice 查询可能导致慢（后续用索引/缓存优化，但不能牺牲契约正确性）。
- UI apply：lightweight-charts 不支持高频“删除头部”，需要明确 rebase 策略，否则体验卡顿或逻辑复杂化。

### 回滚
- 后端新增能力默认关闭：`TRADE_CANVAS_ENABLE_REPLAY_V1=0`（建议）
- 前端 replay UI 默认关闭：`VITE_ENABLE_REPLAY_V1=0`（建议）
- 任一阶段可通过 `git revert <commit>` 回退到不暴露 replay 的状态。

## 验收标准

- 契约一致：`ReplayFrameV1` 的对齐门禁明确且可测试。
- 同输入同输出：固定 fixtures 下，指定 `t` 的帧输出关键字段一致。
- 最小化增删：forward 播放时不触发 `setData`（只 `update`），seek/rewind 只触发一次 `setData` rebase。
- fail-safe：人为制造 out-of-sync（例如 draw head < factor head）时，replay 帧必须返回 `ledger_out_of_sync`。

## E2E 用户故事（门禁）

### Story ID / E2E Test Case（必须）
- Story ID（建议）：`2026-02-02/replay/frame-forward-seek`
- 关联 Plan：`docs/plan/2026-02-02-replay-engine-v1.md`
- E2E 测试用例（建议先后端集成测试，后续补 FE+BE E2E）：
  - Test file path: `backend/tests/test_replay_frame_contract_v1.py`（拟）
  - Test name(s): `test_replay_frame_aligns_and_is_idempotent`（拟）
  - Runner：`pytest`

### Persona / Goal
- Persona：研究员（在 UI 中回放一段行情，检查因子产物与叠加是否同源对齐）
- Goal：把 `t` 从 `t0` 播放到 `t0+1`，并在 `seek` 到 `t0+10` 时仍保持 candle 对齐、输出幂等与可复现

### Entry / Exit（明确入口与出口）
- Entry：对同一 `series_id` 连续请求两帧（`t0` 与 `t1=t0+tf`），中途做一次 `seek`（跳到 `t2=t0+10*tf`）
- Exit：每次返回的 `ReplayFrameV1` 满足对齐门禁，且重复请求同 cursor 的 `draw_delta` 可重复 apply（输出不变）

### Concrete Scenario（必须：写“具体数值”，禁止空泛）

- Chart / Symbol:
  - series_id: `binance:futures:BTC/USDT:1m`
  - timezone: UTC
- Initial State：
  - 使用 fixtures 写入至少 12 根闭合 K（示例：`candle_time=1700000000` 起，步长 60 秒）
- Trigger：
  - 请求 `t0=1700000000`
  - 再请求 `t1=1700000060`
  - 再 seek 到 `t2=1700000600`
- Expected observable outcome：
  - 每帧：`frame.time.candle_id == frame.factor_slices.candle_id == frame.draw_delta.to_candle_id`
  - `draw_delta.next_cursor.version_id` 单调不减

### Preconditions（前置条件）
- fixtures：`fixtures/` 下提供一段固定 candles（或直接复用现有 market fixtures）
- 依赖：只需要 backend（pytest 集成测试即可）

### Main Flow（主流程步骤 + 断言）

1) Step：请求 t0 的 replay frame
   - Requests：`GET /api/replay/frame?series_id=...&at_time=1700000000&cursor_version_id=0`
   - Assertions：
     - `time.aligned_time == 1700000000`
     - `time.candle_id` 与 `factor_slices.candle_id / draw_delta.to_candle_id` 完全一致
   - Evidence：pytest 输出 +（可选）保存 json 到 `output/replay/`（拟）

2) Step：请求 t1 的 replay frame（相邻 +1）
   - Requests：`GET /api/replay/frame?...&at_time=1700000060&cursor_version_id=<from_step1>`
   - Assertions：
     - aligned 到 1700000060
     - draw cursor 幂等可重复（同 cursor 重跑响应一致）

3) Step：seek 到 t2（非相邻跳转）
   - Requests：`GET /api/replay/frame?...&at_time=1700000600&cursor_version_id=0`（允许重置 cursor）
   - Assertions：
     - aligned 到 1700000600
     - 返回可用的 `active_ids` 与 `instruction_catalog_patch`（若 fixtures 覆盖到 overlay）

### Produced Data（产生的数据）
- Tables / Files（拟）：
  - `backend/app/overlay_store.sqlite` / `factor_store.sqlite`（或当前实现的 store）
  - `output/replay/frame_t0.json`（可选证据文件）

### Verification Commands（必须可复制运行）
- Command：`pytest -q`
  - Expected：新增用例通过；且包含对齐断言的具体值（candle_id/time）

### Rollback（回滚）
- 最短回滚：移除/关闭 `/api/replay/frame` 与 `draw_delta at_time` 参数；保持现有 `/api/draw/delta` 默认语义不变

## 变更记录
- 2026-02-02: 创建（草稿）

