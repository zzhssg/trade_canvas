---
title: Market Data 收口与模块化（Phase L：WS 消息入口解析统一化）
status: done
owner: codex
created: 2026-02-09
updated: 2026-02-09
---

## 目标

- 把 `/ws/market` 的消息入口校验（消息体形态、`type` 字段）统一收口到 `WsMessageParser`。
- 消除路由层对 `msg.get(...)` 的隐式依赖，减少无效消息导致的异常分支。

## 变更范围

- parser 增强：
  - `/Users/rick/code/trade_canvas/backend/app/market_data/services.py`
  - 新增 `parse_message_type(...)`、`bad_request(...)`、`unknown_message_type(...)`。
- 路由接入：
  - `/Users/rick/code/trade_canvas/backend/app/main.py`
  - `ws_market` 在进入 subscribe/unsubscribe 分支前先走 parser 入口校验。
- 回归测试：
  - `/Users/rick/code/trade_canvas/backend/tests/test_market_data_services.py`
  - 增加 parser 对非法 envelope / 缺失 type / unknown type 的测试。
  - `/Users/rick/code/trade_canvas/backend/tests/test_market_ws.py`
  - 增加端到端 WS 无效消息 bad_request 行为验证。

## E2E 用户故事（门禁）

Persona：交易员或调试脚本通过 WS 接入市场流。  
Goal：发送非法消息时服务端返回稳定 bad_request，不中断后续合法交互。

断言：
1. 非对象消息体返回 `invalid message envelope`；
2. 缺失 `type` 返回 `missing message type`；
3. 未知 `type` 返回 `unknown message type: <type>`；
4. 以上错误返回后，连接仍可继续处理后续消息。

## 验收命令与结果

- `pytest -q backend/tests/test_market_data_services.py backend/tests/test_market_data_contracts.py backend/tests/test_market_candles.py backend/tests/test_market_ws.py backend/tests/test_market_ws_disconnect_releases_ondemand.py backend/tests/test_e2e_user_story_market_sync.py`（28 passed）
- `cd frontend && npx tsc -b --pretty false --noEmit`（pass）
- `bash docs/scripts/doc_audit.sh`（pass）

## 回滚

- 单 commit 回滚：`git revert <sha>`
- 或回退以下文件：
  - `/Users/rick/code/trade_canvas/backend/app/market_data/services.py`
  - `/Users/rick/code/trade_canvas/backend/app/main.py`
