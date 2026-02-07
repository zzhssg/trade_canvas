---
title: 因子 SDK v1（标准化因子开发与账本接入）
status: 开发中
owner:
created: 2026-02-07
updated: 2026-02-07
---

## 背景

当前因子链路已具备 v0 闭环，但因子实现与存储/绘图/策略/回放存在边界混杂：
- head 快照未落库，`/api/factor/slices` 通过临时计算生成
- 策略/回测仍有独立 SMA demo，与主链路割裂
- 复盘包有 builder 但缺少 API 接入

需要统一 SDK 约束，避免“画对了但算错了 / 算对了但链路断了”。

## 目标 / 非目标

### 目标（Do）
- 输出 `factor_sdk_v1` 契约，统一因子实现与写路径接口。
- head 快照纳入 ledger（append-only + seq），读路径只读 ledger。
- 实盘/回放通过同源 ledger 读取（SQLite 为主），满足 fail-safe。

### 非目标（Don’t）
- 不一次性引入 slot-delta/file-ledger 全量复杂度。
- 不引入 forming 进入因子引擎。

## 方案概述

- SDK 结构：`FactorSpec` + `apply_closed(ctx)` + `FactorApplyResult`（history/head）
- 存储：history 事件流 + head 快照表 + series_head_time 门禁
- 读路径：`/api/factor/slices` 只读 ledger；不再临时重算 head
- 策略适配：freqtrade adapter 读取 SQLite ledger（不足则 backfill）
- 回放：overlay replay package API 接入（read/build/status/window）

## 里程碑

- M0：SDK 契约落盘（docs）
- M1：head ledger 落地 + `/api/factor/slices` 只读
- M2：freqtrade adapter 迁移至 ledger（SQLite）
- M3：overlay replay package API 接入

## 任务拆解

- [ ] M0：新增 `docs/core/contracts/factor_sdk_v1.md`
- [ ] M1：新增 head ledger 表与读写 API；迁移 `/api/factor/slices`
- [ ] M2：freqtrade adapter 改为 ledger 读取 + backfill
- [ ] M3：overlay replay package API 接入

## 风险与回滚

- head 快照落库可能引入存储膨胀：先以 SQLite 语义落地，后续再引入 compaction。
- SDK 迁移期可保留旧 orchestrator 作为 fallback（feature flag）。

## 验收标准

- `seed ≡ incremental` 对拍通过（至少 pivot/pen/zhongshu）。
- `series_head_time < aligned` 时读路径拒绝输出（409 或 build_required）。
- freqtrade adapter 读取 ledger 后能输出一次 enter_long（dry-run）。

## E2E 用户故事（门禁）

> 采用 `tc-e2e-gate` 口径，以下为 v1 草案。

### Story ID
- `2026-02-07/factor-sdk/ledger-freqtrade-dryrun`

### Persona / Goal
- Persona：策略开发者
- Goal：同一份 K 线输入稳定产出因子 ledger，并被 freqtrade adapter 消费产生 dry-run 信号

### Entry / Exit
- Entry：向 `POST /api/market/ingest/candle_closed` 注入固定 K 线序列
- Exit：
  - `/api/factor/slices?at_time=780` 含 pivot/pen/zhongshu
  - freqtrade adapter 输出一次 `enter_long==1`

### Concrete Scenario（具体数值）
- series_id：`binance:futures:BTC/USDT:1m`
- candle_time：`60*(i+1)`，共 13 根
- closes：`[1,2,5,2,1,2,5,2,1,2,5,2,1]`

### Main Flow（步骤 + 断言 + 证据）
1) ingest candles
   - Action：依次调用 `POST /api/market/ingest/candle_closed`
   - Assert：`GET /api/market/candles` 返回最新 `candle_time == 780`
   - Evidence：pytest 断言
2) factor slices
   - Action：`GET /api/factor/slices?series_id=...&at_time=780`
   - Assert：`pivot.history.major.length >= 1`；`pen.history.confirmed.length >= 1`
   - Evidence：pytest 断言
3) freqtrade adapter
   - Action：运行 pytest 中的 adapter 用例
   - Assert：DataFrame 出现一次 `enter_long==1`
   - Evidence：pytest 断言
4) fail-safe
   - Action：人工推进 candle 但不推进 ledger
   - Assert：adapter 必须返回 ok=false 或 enter_long==0

### Evidence（命令）
- `python -m pytest -q`

## 变更记录
- 2026-02-07: 创建（草稿）
