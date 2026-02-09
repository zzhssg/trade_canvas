---
title: WorldState/WorldDelta v1（统一世界状态与差分：live/replay 一套实现）
status: done
owner:
created: 2026-02-03
updated: 2026-02-09
---

## 背景

当前 trade_canvas 的前后端已经具备：
- 因子切片（调试读口）：`GET /api/factor/slices`
- 绘图增量读口：`GET /api/draw/delta`（兼容投影）
- 回放帧契约：`docs/core/contracts/replay_frame_v1.md`

但在产品语义上我们需要一个更明确、更统一的抽象：

> **世界状态 = 当下因子数据 + 当下绘图**

并且要求 **实盘与复盘不做两套实现**：只做场景区分（时间推进方式）与数据源区分（在线真源 vs 回放包/离线数据）。

## 目标 / 非目标

### 目标（Do）

1) 定义统一输出：`WorldStateV1`（世界状态帧）+ `WorldDeltaV1`（世界增量差分）。
2) 实盘模式（live）：
   - 启动：一次性加载 `WorldStateV1(latest)`
   - 运行：每根闭合 K 消费 `WorldDelta` 增量（poll/WS），只做差值加载
3) 复盘模式（replay）：
   - 任意 `t` 定点获取 `WorldStateV1(t)`
   - 支持数据复用：回放包（checkpoint + diffs）一次性/分片加载，前端切片与查询
4) 对齐与门禁：
   - `candle_id` 对齐必须 fail-safe（不一致返回 `ledger_out_of_sync`）
   - `seed ≡ incremental`、cursor 幂等

### 非目标（Don’t）

- v1 不直接落盘终局 `DeltaLedger` 的全部形态（允许先用投影组合出 WorldState/WorldDelta）。
- v1 不强制一次性实现 replay-package 的压缩/索引/分片下载（先定义协议与最小可跑通闭环）。

## 方案概述（最符合软件工程原则的架构）

核心思想（trade_system 批判性继承）：
- 统一对外契约（frame/delta），live 与 replay **只在 at_time 的来源/推进方式不同**
- 真源与派生产物分离：ledger/delta ledger 是真源；frame/package 是可投影可重建产物

### 统一契约
- `WorldStateV1`：`docs/core/contracts/world_state_v1.md`
- `WorldDeltaV1`：`docs/core/contracts/world_delta_v1.md`

### 统一路由命名（避免 “live 走 replay” 的语义混淆）

建议 API 命名为中性 `frame/delta`，而不是 `replay/frame`：

- `GET /api/frame/live?series_id=...` → `WorldStateV1`（最新帧）
- `GET /api/frame/at_time?series_id=...&at_time=t` → `WorldStateV1`（定点帧）
- `GET /api/delta/poll?series_id=...&after_id=...&limit=...` → `WorldDeltaRecordV1[]`（增量差分）
- `GET /api/replay/package?series_id=...&t0=...&t1=...` → `ReplayPackageV1`（后续里程碑）

说明：live/replay 只影响“at_time 如何获得/如何推进”，不影响输出结构。

## 里程碑

### M0：契约落盘（WorldState/WorldDelta）
- 改什么：
  - `docs/core/contracts/world_state_v1.md`
  - `docs/core/contracts/world_delta_v1.md`
  - 本 plan
- 怎么验收：`bash docs/scripts/doc_audit.sh`
- 怎么回滚：`git revert`（仅文档）

### M1：后端 frame 读口（投影组合实现）
- 改什么：
  - 新增 `GET /api/frame/live`（组合 `factor/slices + draw/delta` 的投影）
  - 新增 `GET /api/frame/at_time`（以 `at_time` 对齐点为上限生成 draw_state）
- 怎么验收：
  - pytest：对齐门禁（`frame.time.candle_id == factor_slices.candle_id == draw_state.to_candle_id`）
  - `pytest -q`
- 怎么回滚：保留旧读口；删掉新路由即可

### M2：前端统一消费 frame（消灭 live/replay 两套 apply）
- 改什么：
  - 抽出 `ChartEngine.applyFrame(frame)`（只做 apply，不做业务推理）
  - live/replay 只切换 “frame 的 at_time 来源”（WS latest vs slider）
- 怎么验收：`cd frontend && npm run build` + Playwright 最小用例不回归
- 怎么回滚：feature flag 切回旧路径

### M3：WorldDelta（差分）最小闭环（先投影，后落盘）
- 改什么：
  - `GET /api/delta/poll` 返回每根闭合 K 的 `WorldDeltaRecordV1`（v1 可先只包含 draw_delta）
  - 前端 live 使用 poll/WS 只拉差分
- 怎么验收：cursor 幂等 + `seed ≡ incremental`（pytest）
- 怎么回滚：保留 `frame/live` 作为全量兜底

### M4：ReplayPackage（数据复用）
- 改什么：`GET /api/replay/package`（checkpoint + diffs + index），前端一次性加载后本地切片
- 怎么验收：同 fixtures 重跑，frame(t) 一致；seek 性能与窗口重建正确
- 怎么回滚：回放仍可走 `frame/at_time` 点查投影

## 风险与回滚

主要风险：
- 输出契约不统一导致前端出现双实现（live/replay 分叉）
- 对齐门禁缺失导致“画对了但算错了 / 链路断了”
- 回放包若不做 checkpoint/index，会导致前端 seek 性能不可接受

回滚策略：
- 所有新路由保持兼容，不删除旧 `/api/factor/slices`、`/api/draw/delta`
- 前端统一消费 frame 通过 feature flag 控制，可一键切回旧实现

## 验收标准

- live：启动一次性加载 frame，随后每根闭合 K 只消费 delta（不全量重拉）
- replay：给定 t 可稳定取到 frame(t)，并满足对齐门禁
- 同 fixtures 重跑：`(last_candle_id, active_ids, next_cursor.version_id)` 一致

## E2E 用户故事（门禁）

### Story ID / E2E Test Case（必须）
- Story ID：`2026-02-03/world_state/live-replay-unified-frame`
- 关联 Plan：`docs/plan/2026-02-03-world-state-frame-delta-v1.md`
- E2E 测试用例：
  - Test file path（pytest）：`backend/tests/test_e2e_world_state_frame_delta.py`
  - Test name：`world state: live snapshot + delta; replay frame(t)`
  - Runner：pytest

### Persona / Goal
- Persona：策略/结构研究者
- Goal：同一份输入在 live 与 replay 下用同一套 frame/delta 契约稳定驱动 UI（不写两套 apply）

### Entry / Exit
- Entry：
  - 注入一段 `CandleClosed`（series_id 固定）
  - live：请求 `GET /api/frame/live`
  - replay：请求 `GET /api/frame/at_time&at_time=t`
- Exit：
  - `WorldStateV1.time.candle_id` 与 `factor_slices/draw_state` 对齐
  - live 通过 `delta/poll` 得到增量并推进 `to_candle_time`

### Concrete Scenario（具体数值）
- series_id：`binance:futures:BTC/USDT:1m`
- base=60
- closes：`[1,2,5,2,1,2,5,2,1,2,5,2,1]`
- 断言：
  - `frame/live` 返回 `aligned_time == 780`（最后一根）
  - `frame/at_time&t=780` 返回同 `candle_id`

### Verification Commands
- `bash docs/scripts/doc_audit.sh`
- `pytest -q`
- `cd frontend && npm run build`

## 变更记录
- 2026-02-03: 创建（草稿）

