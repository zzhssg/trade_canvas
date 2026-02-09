---
title: Market Data 收口与模块化（Phase N：P0 治理项合并落地）
status: done
owner: codex
created: 2026-02-09
updated: 2026-02-09
---

## 目标

- 一次性完成 K 线 WS 链路的 P0 治理项：协议常量收口、路由职责收口、订阅观测增强、参数配置化、强类型解析。
- 保持现有 HTTP/WS 对外契约语义不变。

## 变更范围

- 协议常量收口：
  - `/Users/rick/code/trade_canvas/backend/app/ws_protocol.py`
  - 新增 WS 消息类型、错误码、错误文案常量与 unknown type 文案函数。
- 错误/解析与订阅协调：
  - `/Users/rick/code/trade_canvas/backend/app/market_data/services.py`
  - `WsMessageParser.parse_subscribe(...)` 改为强类型返回；
  - `handle_subscribe(...)` 增加结构化日志；
  - parser/coordinator 统一复用错误 payload 构造。
- WS 路由职责收口：
  - `/Users/rick/code/trade_canvas/backend/app/market_ws_routes.py`
  - 提供 `handle_market_ws(...)`；主循环处理下沉到独立模块。
  - `/Users/rick/code/trade_canvas/backend/app/main.py`
  - 仅保留 `/ws/market` endpoint 声明并委托 handler。
- 参数配置化：
  - `/Users/rick/code/trade_canvas/backend/app/config.py`
  - 新增 market WS catchup/freshness/gap-read 参数的环境变量配置。
  - `/Users/rick/code/trade_canvas/backend/app/main.py`
  - 接入配置化参数到 orchestrator/backfill/ws state。
- 回归测试：
  - `/Users/rick/code/trade_canvas/backend/tests/test_market_data_services.py`
  - `/Users/rick/code/trade_canvas/backend/tests/test_market_ws.py`

## E2E 用户故事（门禁）

Persona：交易员通过 WS 订阅 K 线，客户端可能发送非法消息，也可能触发容量限制。  
Goal：服务端在保证主链路继续可用的同时，返回稳定错误结构并维持可观测性。

断言：
1. 非法消息 envelope/type 返回稳定 bad_request；
2. 容量限制返回带 `series_id` 的 capacity 错误；
3. 正常 subscribe 路径保持 catchup/live 语义不变；
4. 关键订阅路径输出结构化日志字段（计数与耗时）。

## 验收命令与结果

- `pytest -q --collect-only backend/tests/test_e2e_user_story_market_sync.py`（5 collected）
- `pytest -q backend/tests/test_market_data_services.py backend/tests/test_market_data_contracts.py backend/tests/test_market_candles.py backend/tests/test_market_ws.py backend/tests/test_market_ws_disconnect_releases_ondemand.py backend/tests/test_e2e_user_story_market_sync.py`（31 passed）
- `cd frontend && npx tsc -b --pretty false --noEmit`（pass）
- `bash docs/scripts/doc_audit.sh`（pass）

## 回滚

- 单 commit 回滚：`git revert <sha>`
- 或最小回退：
  - `/Users/rick/code/trade_canvas/backend/app/market_ws_routes.py`
  - `/Users/rick/code/trade_canvas/backend/app/market_data/services.py`
  - `/Users/rick/code/trade_canvas/backend/app/ws_protocol.py`
  - `/Users/rick/code/trade_canvas/backend/app/config.py`
