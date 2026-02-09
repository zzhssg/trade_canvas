---
title: Market Data 收口与模块化（Phase D：Derived 首次回填收口）
status: done
owner: codex
created: 2026-02-09
updated: 2026-02-09
---

## 目标

- 把 WS subscribe 时“derived 序列首次回填”逻辑从 `main.py` 内联代码迁移到 `market_data` 域服务。
- 保持现有外部契约（HTTP/WS 消息）不变，保持行为一致。

## 变更范围

- 新增 `build_derived_initial_backfill_handler(...)`：
  - `/Users/rick/code/trade_canvas/backend/app/market_data/services.py`
  - 统一处理：开关判断、base tail 读取、rollup、落库、factor/overlay sidecar。
- 修改主装配：
  - `/Users/rick/code/trade_canvas/backend/app/main.py`
  - WS subscribe 前仅调用统一 handler，不再保留 derived 内联回填块。
- 扩展测试：
  - `/Users/rick/code/trade_canvas/backend/tests/test_market_data_services.py`
  - 新增 derived 回填行为与开关回归保护。

## E2E 用户故事（门禁）

Persona：交易员首次订阅 `binance:futures:BTC/USDT:5m`（derived）图表。  
Goal：若本地 `5m` 无历史且 `TRADE_CANVAS_ENABLE_DERIVED_TIMEFRAMES=1`，服务端从 `1m` tail rollup 一段 `5m` closed，图表可立即渲染并继续 WS catchup/live。

断言：
1. derived 开关关闭时，不触发 derived 回填；
2. 开关开启且 base 数据充足时，derived 首次回填落库成功；
3. factor/overlay sidecar 按既有口径执行（`rebuilt` 时 reset overlay）。

## 验收命令与结果

- `pytest -q backend/tests/test_market_data_services.py backend/tests/test_market_data_contracts.py backend/tests/test_market_candles.py backend/tests/test_market_ws.py backend/tests/test_e2e_user_story_market_sync.py`
- `pytest -q backend/tests/test_e2e_user_story_market_sync.py`
- `cd frontend && npx tsc -b --pretty false --noEmit`
- `bash docs/scripts/doc_audit.sh`

## 回滚

- 单 commit 回滚：`git revert <sha>`
- 或仅回退 `/Users/rick/code/trade_canvas/backend/app/main.py` 对 `build_derived_initial_backfill_handler(...)` 的接入，恢复内联回填逻辑。
