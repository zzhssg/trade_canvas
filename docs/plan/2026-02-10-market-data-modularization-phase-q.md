---
title: Market Data 收口与模块化（Phase Q：Ingest 应用服务与主装配瘦身）
status: done
owner: codex
created: 2026-02-10
updated: 2026-02-10
---

## 目标

- 将 market HTTP 写链路编排从路由层下沉到应用服务层，降低路由复杂度。
- 将 market runtime 装配从 `main.py` 抽离到 builder，进一步收敛入口文件职责。
- 统一 history bootstrap datadir 配置入口，移除业务代码中的直接环境变量读取。

## 变更范围

- 写链路应用服务下沉：
  - `/Users/rick/code/trade_canvas/backend/app/market_ingest_service.py`
  - `/Users/rick/code/trade_canvas/backend/app/market_http_routes.py`
  - `/Users/rick/code/trade_canvas/backend/app/market_runtime.py`
- market runtime 装配下沉：
  - `/Users/rick/code/trade_canvas/backend/app/market_runtime_builder.py`
  - `/Users/rick/code/trade_canvas/backend/app/main.py`
- 配置口径统一：
  - `/Users/rick/code/trade_canvas/backend/app/config.py`
  - `/Users/rick/code/trade_canvas/backend/app/history_bootstrapper.py`
- 回归测试调整：
  - `/Users/rick/code/trade_canvas/backend/tests/test_market_ws.py`
  - `/Users/rick/code/trade_canvas/backend/tests/test_e2e_user_story_market_sync.py`
  - `/Users/rick/code/trade_canvas/backend/tests/test_config_market_settings.py`
- 文档同步：
  - `/Users/rick/code/trade_canvas/docs/core/market-kline-sync.md`

## E2E 用户故事（门禁）

Persona：交易员在 1m 图上持续接收闭合 K 线。  
Goal：HTTP ingest 写入后，策略/绘图 sidecar 与 WS 广播行为保持一致；订阅期间 gap 回补仍按既定顺序输出。

断言：
1. `POST /api/market/ingest/candle_closed` 行为不变（包含 rebuild 消息与 debug 事件）；
2. `POST /api/market/ingest/candle_forming` 在 debug 开关开启时仍可广播 forming；
3. `/ws/market` 的 gap 回补与 catchup/live 推送行为与此前一致；
4. `history_bootstrapper` 在设置 datadir 时可正确加载 feather 数据。

## 验收命令与结果

- `pytest -q backend/tests/test_config_market_settings.py backend/tests/test_market_ws.py backend/tests/test_e2e_user_story_market_sync.py backend/tests/test_market_runtime_routes.py backend/tests/test_market_candles.py backend/tests/test_market_data_services.py backend/tests/test_history_bootstrapper.py backend/tests/test_market_debug_ingest_state.py backend/tests/test_market_top_markets.py backend/tests/test_market_top_markets_sse.py backend/tests/test_market_ws_disconnect_releases_ondemand.py backend/tests/test_ingest_supervisor_capacity.py backend/tests/test_ingest_supervisor_whitelist_fallback.py`（43 passed）
- `pytest -q backend/tests/test_e2e_user_story_market_sync.py`（5 passed）
- `cd frontend && npx tsc -b --pretty false --noEmit`（pass）
- `bash docs/scripts/doc_audit.sh`（pass）

## 回滚

- 代码回滚：`git revert <sha>`
- 最小文件回退：
  - `/Users/rick/code/trade_canvas/backend/app/market_ingest_service.py`
  - `/Users/rick/code/trade_canvas/backend/app/market_runtime_builder.py`
  - `/Users/rick/code/trade_canvas/backend/app/market_runtime.py`
  - `/Users/rick/code/trade_canvas/backend/app/market_http_routes.py`
  - `/Users/rick/code/trade_canvas/backend/app/main.py`
  - `/Users/rick/code/trade_canvas/backend/app/config.py`
  - `/Users/rick/code/trade_canvas/backend/app/history_bootstrapper.py`
