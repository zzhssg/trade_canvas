---
title: Market Data 收口与模块化（Phase P：服务拆分与配置统一）
status: done
owner: codex
created: 2026-02-10
updated: 2026-02-10
---

## 目标

- 解决 `market_data/services.py` 单文件过大问题，按职责拆分为 read/orchestrator/ws/derived 四个模块。
- 统一 market K 线链路环境变量读取口径，减少重复 parse 与跨文件漂移。
- 保持 HTTP/WS 对外契约与 E2E 用户故事不变。

## 变更范围

- 市场数据子模块拆分：
  - `/Users/rick/code/trade_canvas/backend/app/market_data/read_services.py`
  - `/Users/rick/code/trade_canvas/backend/app/market_data/orchestrator.py`
  - `/Users/rick/code/trade_canvas/backend/app/market_data/ws_services.py`
  - `/Users/rick/code/trade_canvas/backend/app/market_data/derived_services.py`
  - 删除 `/Users/rick/code/trade_canvas/backend/app/market_data/services.py`，不再保留兼容转发层
  - `/Users/rick/code/trade_canvas/backend/app/market_data/__init__.py`
- 配置解析统一：
  - `/Users/rick/code/trade_canvas/backend/app/market_flags.py`
  - `/Users/rick/code/trade_canvas/backend/app/market_http_routes.py`
  - `/Users/rick/code/trade_canvas/backend/app/market_ws_routes.py`
  - `/Users/rick/code/trade_canvas/backend/app/market_meta_routes.py`
  - `/Users/rick/code/trade_canvas/backend/app/ingest_supervisor.py`
  - `/Users/rick/code/trade_canvas/backend/app/market_backfill.py`
  - `/Users/rick/code/trade_canvas/backend/app/history_bootstrapper.py`
  - `/Users/rick/code/trade_canvas/backend/app/main.py`
- 回归测试与文档：
  - `/Users/rick/code/trade_canvas/backend/tests/test_market_data_services.py`
  - `/Users/rick/code/trade_canvas/docs/core/market-kline-sync.md`

## E2E 用户故事（门禁）

Persona：交易员订阅 `binance:futures:BTC/USDT:1m` 并期望历史+实时连续。  
Goal：在保持现有 HTTP/WS 契约不变的前提下，完成 K 线读取、gap 回补、增量推送与 on-demand 容量控制。

断言：
1. `/api/market/candles` 仍可执行 tail 读取与 since 增量读取；
2. `/ws/market` subscribe 仍可返回 `candle_closed` / `candles_batch` / `gap`；
3. live gap 回补仍按 `gap -> best-effort backfill -> recover emit` 顺序执行；
4. on-demand capacity / disconnect cleanup 行为保持一致；
5. 配置项非法值仍按既定下限钳制。

## 验收命令与结果

- `pytest -q backend/tests/test_market_data_services.py backend/tests/test_market_candles.py backend/tests/test_market_ws.py backend/tests/test_market_ws_disconnect_releases_ondemand.py backend/tests/test_e2e_user_story_market_sync.py backend/tests/test_history_bootstrapper.py backend/tests/test_ingest_supervisor_capacity.py backend/tests/test_ingest_supervisor_whitelist_fallback.py backend/tests/test_market_runtime_routes.py backend/tests/test_market_debug_ingest_state.py backend/tests/test_market_top_markets.py backend/tests/test_market_top_markets_sse.py`（40 passed）
- `pytest -q backend/tests/test_e2e_user_story_market_sync.py`（5 passed）
- `cd frontend && npx tsc -b --pretty false --noEmit`（pass）
- `bash docs/scripts/doc_audit.sh`（pass）

## 回滚

- 代码回滚：`git revert <sha>`
- 最小文件回退：
  - `/Users/rick/code/trade_canvas/backend/app/market_data/`
  - `/Users/rick/code/trade_canvas/backend/app/market_flags.py`
  - `/Users/rick/code/trade_canvas/backend/app/market_http_routes.py`
  - `/Users/rick/code/trade_canvas/backend/app/market_ws_routes.py`
  - `/Users/rick/code/trade_canvas/backend/app/market_meta_routes.py`
  - `/Users/rick/code/trade_canvas/backend/app/ingest_supervisor.py`
  - `/Users/rick/code/trade_canvas/backend/app/market_backfill.py`
  - `/Users/rick/code/trade_canvas/backend/app/history_bootstrapper.py`
  - `/Users/rick/code/trade_canvas/backend/app/main.py`
