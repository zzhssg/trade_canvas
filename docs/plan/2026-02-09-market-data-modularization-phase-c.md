---
title: Market Data 收口与模块化（Phase C：Gap Backfill 中心化）
status: done
owner: codex
created: 2026-02-09
updated: 2026-02-09
---

## 目标

- 把 `main.py` 中内联的 `gap -> best-effort backfill -> read-between` 逻辑迁移到 `market_data` 域服务。
- 保持 HTTP/WS 对外协议与行为不变，确保可回滚。

## 变更范围

- 新增 `StoreBackfillService` 与 `build_gap_backfill_handler`：
  - `/Users/rick/code/trade_canvas/backend/app/market_data/services.py`
  - `ensure_tail_coverage(series_id, target_candles, to_time)` 按目标窗口返回覆盖条数
- 导出新能力：
  - `/Users/rick/code/trade_canvas/backend/app/market_data/__init__.py`
- 接入主链路装配：
  - `/Users/rick/code/trade_canvas/backend/app/main.py`
  - 由 `main.py` 注入 reader/backfill 到统一 handler，不再写内联 gap 回补闭包。
- 回归测试：
  - `/Users/rick/code/trade_canvas/backend/tests/test_market_data_services.py`

## E2E 用户故事（门禁）

Persona：交易员在 `1m` 图上从 `since=100` 订阅，服务端 live 收到 `220`，中间 `160` 缺失。  
Goal：当 `TRADE_CANVAS_ENABLE_MARKET_GAP_BACKFILL=1` 时，服务端先 best-effort 回补并回读 `160`，再下发 `220`；若回补失败仍发 `gap` 事件。

断言：
1. gap 回补开关关闭时，不触发回补处理器；
2. 开关开启且回补成功时，回读结果包含缺口区间 candle；
3. 现有 WS E2E 用例仍通过（无重复/无乱序）。

## 验收命令与结果

- `pytest -q backend/tests/test_market_data_services.py backend/tests/test_market_data_contracts.py backend/tests/test_market_candles.py backend/tests/test_market_ws.py backend/tests/test_e2e_user_story_market_sync.py`
- `pytest -q backend/tests/test_e2e_user_story_market_sync.py`
- `cd frontend && npx tsc -b --pretty false --noEmit`
- `bash docs/scripts/doc_audit.sh`

## 回滚

- 单 commit 回滚：`git revert <sha>`
- 或仅回退 `/Users/rick/code/trade_canvas/backend/app/main.py` 对 `build_gap_backfill_handler(...)` 的接入，恢复旧内联闭包。
