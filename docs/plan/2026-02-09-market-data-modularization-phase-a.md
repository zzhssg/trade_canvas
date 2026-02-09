---
title: Market Data 收口与模块化（Phase A：契约收口）
status: done
owner: codex
created: 2026-02-09
updated: 2026-02-09
---

## 背景

当前 K 线链路（下载/补齐/读取/WS 推送）分散在 `main.py`、`ws_hub.py`、`ingest_binance_ws.py`、`history_bootstrapper.py`、`market_backfill.py`。在功能迭代后，治理成本上升，存在口径漂移风险。

## 目标 / 非目标

### 目标
- 建立 `market_data` 领域契约，作为后续收口唯一对齐点。
- 明确 5 类能力边界：读取、补齐、新鲜度、WS 交付、总编排。
- 在不改变线上行为的前提下完成 Phase A 落地。

### 非目标
- 本阶段不改变 API/WS 行为。
- 本阶段不迁移 `main.py`/`ws_hub.py` 现有执行逻辑。
- 本阶段不做数据库 schema 变更。

## 方案概述

新增 `backend/app/market_data/contracts.py`，定义领域接口与数据结构：
- `CandleReadService`
- `BackfillService`
- `FreshnessService`
- `WsDeliveryService`
- `MarketDataOrchestrator`

并在 `docs/core/market-kline-sync.md` 增补“模块收口目标结构”说明，作为后续 Phase B/C 的真源。

## 里程碑

1. M1（本阶段）：契约与文档收口，不改行为。
2. M2（后续）：读取链路迁移到 `read_service`。
3. M3（后续）：补齐链路迁移到 `backfill_service`。
4. M4（后续）：新鲜度治理中心化。

## 任务拆解
- [x] 新增 `market_data/contracts.py` 契约定义。
- [x] 新增 `market_data/__init__.py` 导出。
- [x] 增加契约级测试 `test_market_data_contracts.py`。
- [x] 更新 `docs/core/market-kline-sync.md` 收口章节。
- [x] 修正文档中 `since` 语义与实现一致（`>`）。

## 风险与回滚

风险：
- 契约命名不当会导致后续迁移成本上升。

回滚：
- 纯新增文件/文档，单个 commit 可 `git revert <sha>` 回退。

## 验收标准

- `pytest -q backend/tests/test_market_data_contracts.py`
- `pytest -q backend/tests/test_market_candles.py backend/tests/test_market_ws.py`
- `bash docs/scripts/doc_audit.sh`

## E2E 用户故事（门禁）

Persona：交易员在图表页切换 `binance:futures:BTC/USDT:1m`。  
目标：先读取 tail，再通过 WS 追平与持续更新，不出现重复或错序。

主流程：
1. HTTP 拉取 `GET /api/market/candles?series_id=...&limit=2000`。
2. WS 订阅 `subscribe{series_id,since=last_time}`。
3. 后端推送 catchup（可空）+ live `candle_closed`。
4. 若时间跳跃，按策略先尝试回补，无法补齐再发 `gap`。

断言：
- candle_time 单调递增；
- 同一 candle_time 最终只有 1 条有效数据；
- 出现 gap 时有可观测事件（`gap` 或回补后的连续 candles）。

## 变更记录
- 2026-02-09: 创建并落地 Phase A（契约收口）
