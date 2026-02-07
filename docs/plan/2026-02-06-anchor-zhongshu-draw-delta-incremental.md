---
title: 锚因子 + 中枢因子（增量计算 + draw/delta 绘图）
status: 已完成
owner:
created: 2026-02-06
updated: 2026-02-07
---

## 背景

trade_canvas 已具备 pivot/pen/zhongshu/anchor 的事件落库与 factor_slices 读口，但仍存在：
- 因子 ingest 仍是“全量回算 + 去重写入”，不满足严格增量计算诉求。
- draw/delta 只覆盖 pivot/pen，前端缺少中枢/锚的绘图与 sub_feature 筛选。
- anchor 的强度切换仍限制在 confirmed pen（需要允许 candidate 强度触发）。

## 目标 / 非目标

### 目标
- 严格增量：仅处理新 closed candles，不再全量重算历史。
- 锚点切换：支持 strong_pen（候选/确认）与 zhongshu_entry 两种触发方式。
- draw/delta：新增 zhongshu/anchor 绘图指令，前端可见且可筛选。
- 可复现：同一输入，seed ≡ incremental。

### 非目标
- 不引入完整 factor ledger/slot delta ledger。
- 不实现完整背驰/趋势线等高级因子。

## 方案概述

- 后端：
  - 引入增量处理逻辑：按 candle_time 逐根推进 pivot/pen/zhongshu/anchor。
  - 复用 factor_slices 逻辑，产出 zhongshu/anchor 快照。
  - overlay_orchestrator 产出 zhongshu/anchor 的 polyline 指令。
- 前端：
  - factor catalog 增加 zhongshu/anchor 子项。
  - ChartView 渲染 overlay polyline，支持 sub_feature 过滤。

## 里程碑

- M0 文档/契约更新
- M1 严格增量因子 ingest
- M2 draw/delta 中枢/锚绘图
- M3 前端渲染与筛选
- M4 E2E 门禁

## 任务拆解
- [ ] 新增 plan 文档与 anchor 契约修订
- [ ] 因子 ingest 改为增量处理
- [ ] overlay_orchestrator 生成 zhongshu/anchor polyline 指令
- [ ] 前端 factor catalog + ChartView 渲染支持
- [ ] 新增回归测试并跑门禁

## 风险与回滚

- 风险：增量逻辑错误导致 seed ≠ incremental；锚切换过于频繁。
- 回滚：保留旧实现分支，可用 `git revert` 回退；`TRADE_CANVAS_ENABLE_FACTOR_INGEST=0` 可禁用因子写入。

## 验收标准

- `pytest -q` 通过。
- `cd frontend && npm run build` 通过。
- `bash docs/scripts/doc_audit.sh` 通过。
- E2E 计划脚本可运行（`E2E_PLAN_DOC=... bash scripts/e2e_acceptance.sh`）。

## E2E 用户故事（门禁）

Persona：结构因子研究者

Goal：给定一段 `CandleClosed[]`，一次性加载 + 流式更新后，因子与绘图结果保持同源、可复现。

### Entry

- `POST /api/market/ingest/candle_closed`
- series_id：`binance:futures:BTC/USDT:1m`

### Flow

1) 注入固定序列 candles（复用 `backend/tests/test_zhongshu_dead_factor.py` 价格序列）。
2) `GET /api/factor/slices?series_id=...&at_time=1260`：
   - `zhongshu.head.alive` 与 `history.dead` 符合可见性门禁。
   - `anchor.history.switches` 同时包含 `strong_pen` 与 `zhongshu_entry`。
3) 追加两根新 K 线，`/api/factor/slices` 与 `/api/draw/delta` 输出更新。
4) 前端勾选/关闭 `zhongshu.*`/`anchor.*` 子项时，图形显隐同步更新。

### Exit（断言）

- `snapshots["zhongshu"].head.alive.length in {0,1}`，且 `formed_time<=at_time`。
- `snapshots["anchor"].history.switches` 含 `strong_pen` 与 `zhongshu_entry`。
- `/api/draw/delta` 的 `instruction_catalog_patch` 包含 `zhongshu.*` 与 `anchor.*` polyline。
- UI data-attrs：`data-zhongshu-count>0` / `data-anchor-on=1`。

### Evidence

- `pytest -q`
- `cd frontend && npm run build`
- `E2E_PLAN_DOC=docs/plan/2026-02-06-anchor-zhongshu-draw-delta-incremental.md bash scripts/e2e_acceptance.sh`

## 变更记录
- 2026-02-06: 创建（草稿）
