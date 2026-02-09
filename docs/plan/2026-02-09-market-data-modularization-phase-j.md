---
title: Market Data 收口与模块化（Phase J：订阅主流程统一入口）
status: done
owner: codex
created: 2026-02-09
updated: 2026-02-09
---

## 目标

- 继续瘦身 `ws_market` 路由，把 subscribe 主流程统一下沉到 `WsSubscriptionCoordinator`。
- 保持 WS 对外协议与 race 语义不变，避免重复推送或 `last_sent` 漂移。

## 变更范围

- 主流程收口：
  - `/Users/rick/code/trade_canvas/backend/app/market_data/services.py`
  - `WsSubscriptionCoordinator` 新增 `handle_subscribe(...)`，统一编排回填、订阅、catchup、emit 和 `last_sent` 更新。
- 路由瘦身：
  - `/Users/rick/code/trade_canvas/backend/app/main.py`
  - subscribe 分支改为调用 `handle_subscribe(...)`，路由层仅负责协议校验和发包。
- 回归测试：
  - `/Users/rick/code/trade_canvas/backend/tests/test_market_data_services.py`
  - 增加 coordinator 主流程测试，覆盖 payload 输出和 `last_sent` 更新。

## E2E 用户故事（门禁）

Persona：交易员订阅 `BTC/USDT:1m`，期望在首次订阅时拿到稳定的 catchup 数据且不重复。  
Goal：subscribe 一次后，服务端完成回填与增量过滤，返回可直接发送的 payload，并更新 `last_sent`。

断言：
1. `handle_subscribe(...)` 成功时返回 `payloads`，且包含 `candle_closed/candles_batch` 之一；
2. `last_sent` 以发包最后一根 candle 时间更新；
3. 路由层不再内联 catchup/emit 编排逻辑，只做 send 循环。

## 验收命令与结果

- `pytest -q backend/tests/test_market_data_services.py backend/tests/test_market_data_contracts.py backend/tests/test_market_candles.py backend/tests/test_market_ws.py backend/tests/test_market_ws_disconnect_releases_ondemand.py backend/tests/test_e2e_user_story_market_sync.py`（26 passed）
- `cd frontend && npx tsc -b --pretty false --noEmit`（pass）
- `bash docs/scripts/doc_audit.sh`（pass）

## 回滚

- 单 commit 回滚：`git revert <sha>`
- 或回退以下文件：
  - `/Users/rick/code/trade_canvas/backend/app/market_data/services.py`
  - `/Users/rick/code/trade_canvas/backend/app/main.py`
