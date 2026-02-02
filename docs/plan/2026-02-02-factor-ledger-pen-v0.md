---
title: FactorStore/FactorLedger v0（Pivot.major + 确认笔 Pen.confirmed）
status: done
owner:
created: 2026-02-02
updated: 2026-02-02
---

## 背景

现状：
- 已有市场真源：`candles`（SQLite），由 `CandleClosed` 驱动写入/WS 推送。
- 已有绘图产物：`plot_overlay_events`（pivot.major/minor 事件，延迟确认，可画回 pivot_time）。
- 缺口：没有“因子快照/ledger”层，无法回答“t 时刻有哪些因子/因子快照是什么”，也无法承载更高阶结构（如确认笔）的一致性与回放。

trade_system 参考（只继承不变量，不抄实现负债）：
- 主键用 `candle_time`，history append-only；head 可短窗重算；无未来函数；`seed ≡ incremental`。
- “确认笔”语义：当出现下一根反向 pivot 时，上一根结构笔才下沉为 confirmed（append-only）。

## 目标 / 非目标

### 目标（Do）
- 引入最小可落地的 FactorStore/FactorLedger（SQLite），支持：
  - `pivot`：持久化 `major`（history，延迟确认）
  - `pen`：持久化 `confirmed`（history，延迟确认），由 pivot.major 驱动
- 提供可查询 API：`GET /api/factor/slices?series_id=...&at_time=...` 返回 `FactorSliceV1`（pivot + pen）。
- 保持实现精简、可测试、可回滚，不引入 replay/slot-delta 复杂度。

### 非目标（Don’t）
- 不做完整 factor2 registry/deps_snapshot 拓扑闭包（v0 只做 pivot+pen 两个因子）。
- 不做文件 ledger/compaction（v0 先用 SQLite 表表达 append-only 语义）。
- 不做完整 head（v0 仅 pivot.head.minor 做短窗重算；pen.head 暂空）。

## 方案概述

### 1) FactorStore（SQLite）

新增表（与 `candles` 共用同一个 `TRADE_CANVAS_DB_PATH`）：
- `factor_series_state(series_id, head_time, updated_at_ms)`
- `factor_events(id, series_id, factor_name, candle_time, kind, event_key, payload_json, created_at_ms, UNIQUE(series_id,factor_name,event_key))`

语义：
- `candle_time` 即事件的 `visible_time`（确认可见时刻）。
- 去重依赖 `event_key`（例如 pivot:idx:dir:window；pen:start_idx:end_idx:dir）。

### 2) FactorLedger（查询）

`GET /api/factor/slices`：
- 先将 `at_time` 对齐到 `<=at_time` 的最近 `candle_time`（避免请求落在缺失时间点）。
- `pivot`：
  - `history.major`: 从 `factor_events` 读取可见事件（`candle_time<=t`）
  - `head.minor`: 基于 `candles` + segment_start（last major pivot）进行短窗重算（无未来函数）
- `pen`：
  - `history.confirmed`: 从 `factor_events` 读取可见事件（`candle_time<=t`）

### 3) 确认笔（Pen.confirmed）逻辑（精简）

输入：pivot.major（已延迟确认的极值点）。

核心规则（对齐 trade_system 口径）：
- 连续同向 pivot：只保留更极端的一个（effective pivot 替换）。
- 当出现反向 pivot（effective pivot 追加）：
  - 若 effective pivots 数量 >= 3，则确认上一根结构笔：
    - `pen = (effective[-3] -> effective[-2])`
    - `visible_time = effective[-1].visible_time`（由“下一根反向 pivot”确认）
    - append-only 落盘（idempotent 去重）

## E2E 用户故事（必须覆盖主流程）

### Persona / Goal
- Persona：策略开发者
- Goal：给定一段 K 线，能在 t 时刻查询到 pivot 与确认笔（pen.confirmed）快照

### Main Flow + Assertions
1) 注入一段 `CandleClosed`（HTTP ingest），构造至少 3 个交替的 major pivots（从而至少确认 1 根 pen）
2) `GET /api/factor/slices?series_id=...&at_time=<t>`
   - `snapshots.pivot.history.major` 非空
   - `snapshots.pen.history.confirmed` 非空
   - 每条 pen 的 `visible_time <= t`
3) 同一份输入重复运行（重启 app 或重复 ingest）：
   - 不产生重复事件（去重 key 不变）

### Verification Commands
- `python3 -m pytest -q`
- `E2E_PLAN_DOC="docs/plan/2026-02-02-factor-ledger-pen-v0.md" bash scripts/e2e_acceptance.sh`

## 里程碑

- [x] M0：FactorStore schema + CRUD + 最小事件落盘
- [x] M1：Pivot.major 写入 FactorStore（复用已有 pivot 计算）
- [x] M2：Pen.confirmed 计算与落盘（append-only + 去重）
- [x] M3：FactorLedger slices API + 测试 + Playwright 门禁通过

## 变更记录
- 2026-02-02: 创建（开发中）
- 2026-02-02: 验收通过（pytest + Playwright E2E + plan status gate），状态更新为 done
