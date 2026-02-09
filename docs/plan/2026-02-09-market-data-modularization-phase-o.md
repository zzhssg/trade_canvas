---
title: Market Data 收口与模块化（Phase O：Market Runtime 单路径）
status: done
owner: codex
created: 2026-02-09
updated: 2026-02-09
---

## 目标

- 将 market HTTP/WS 主链路从 `main.py` 下沉到独立模块，入口文件只保留装配职责。
- 引入 `MarketRuntime` typed container，统一管理 market 依赖，消除 `app.state` 零散读取。
- 固化单路径实现，减少灰度分支与重复逻辑，提升后续治理效率。

## 变更范围

- 运行时容器：
  - `/Users/rick/code/trade_canvas/backend/app/config.py`
  - 保留市场同步窗口配置解析，清理与单路径无关的 runtime v2 配置项。
  - `/Users/rick/code/trade_canvas/backend/app/market_runtime.py`
  - 新增 `MarketRuntime` typed container。
- HTTP/WS 路由收口：
  - `/Users/rick/code/trade_canvas/backend/app/market_http_routes.py`
  - 承接 `/api/market/candles`、`/api/market/ingest/candle_closed`、`/api/market/ingest/candle_forming`。
  - `/Users/rick/code/trade_canvas/backend/app/market_meta_routes.py`
  - 改为从 `market_runtime` 读取 whitelist、ingest_supervisor、market_list、force_limiter。
  - `/Users/rick/code/trade_canvas/backend/app/market_ws_routes.py`
  - 改为统一从 `market_runtime` 读取 ws parser / subscribe coordinator / market_data。
  - `/Users/rick/code/trade_canvas/backend/app/main.py`
  - 删除 market HTTP 旧内联实现，统一注册模块化路由。
  - 新增 `draw_routes` / `debug_routes` 调用，进一步收口入口文件职责。
- 回归测试：
  - `/Users/rick/code/trade_canvas/backend/tests/test_market_runtime_routes.py`
  - `/Users/rick/code/trade_canvas/backend/tests/test_config_market_settings.py`
  - `/Users/rick/code/trade_canvas/backend/tests/test_market_data_services.py`
  - `/Users/rick/code/trade_canvas/backend/tests/test_market_ws.py`

## E2E 用户故事（门禁）

Persona：交易员打开 `BTC/USDT 1m` 图表并订阅实时 K 线。  
Goal：HTTP 拉取、WS catchup、实时推送都走统一 market runtime，行为稳定且无主链路漂移。

断言：
1. `/api/market/candles`、`/api/market/ingest/*` 能在模块化路由下稳定工作；
2. `/ws/market` subscribe catchup 仍返回闭合 K 线序列，且依赖来自统一 runtime；
3. `GET /api/market/whitelist`、`/api/market/top_markets` 等 meta 接口在 runtime 容器下行为不变；
4. draw/debug 路由下沉后，入口文件不再承载领域逻辑。

## 验收命令与结果

- `pytest -q backend/tests/test_draw_delta_api.py backend/tests/test_market_debug_ingest_state.py backend/tests/test_market_debug_candle_forming.py backend/tests/test_market_top_markets.py backend/tests/test_market_top_markets_sse.py backend/tests/test_market_ws.py backend/tests/test_market_candles.py backend/tests/test_e2e_user_story_market_sync.py backend/tests/test_market_runtime_routes.py backend/tests/test_config_market_settings.py`（34 passed）
- `pytest -q backend/tests/test_market_data_services.py backend/tests/test_market_data_contracts.py backend/tests/test_market_ws_disconnect_releases_ondemand.py`（17 passed）
- `bash docs/scripts/doc_audit.sh`（pass，HTTP/WS 文档完整性校验通过）

## 回滚

- 代码回滚：`git revert <sha>`
- 最小文件回退：
  - `/Users/rick/code/trade_canvas/backend/app/config.py`
  - `/Users/rick/code/trade_canvas/backend/app/market_runtime.py`
  - `/Users/rick/code/trade_canvas/backend/app/market_http_routes.py`
  - `/Users/rick/code/trade_canvas/backend/app/market_meta_routes.py`
  - `/Users/rick/code/trade_canvas/backend/app/market_ws_routes.py`
  - `/Users/rick/code/trade_canvas/backend/app/main.py`
