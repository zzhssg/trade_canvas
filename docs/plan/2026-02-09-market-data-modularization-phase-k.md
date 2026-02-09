---
title: Market Data 收口与模块化（Phase K：WS 消息校验集中化）
status: done
owner: codex
created: 2026-02-09
updated: 2026-02-09
---

## 目标

- 继续瘦身 `ws_market` 路由，把 subscribe/unsubscribe 的参数校验逻辑统一收口到 `market_data`。
- 统一 bad_request 错误口径，避免校验规则散落在路由实现中。

## 变更范围

- 新增消息解析器：
  - `/Users/rick/code/trade_canvas/backend/app/market_data/services.py`
  - 增加 `WsMessageParser`，负责 subscribe/unsubscribe 参数解析与校验。
- 对外导出与契约补充：
  - `/Users/rick/code/trade_canvas/backend/app/market_data/contracts.py`
  - 新增 `WsSubscribeCommand`。
  - `/Users/rick/code/trade_canvas/backend/app/market_data/__init__.py`
  - 导出 `WsMessageParser/WsSubscribeCommand`。
- 路由接入：
  - `/Users/rick/code/trade_canvas/backend/app/main.py`
  - `ws_market` 使用解析器结果驱动后续订阅编排，不再内联字段校验。
- 回归测试：
  - `/Users/rick/code/trade_canvas/backend/tests/test_market_data_services.py`
  - 新增 `WsMessageParser` 的成功/失败路径测试。

## E2E 用户故事（门禁）

Persona：交易员通过 WS 订阅市场序列。  
Goal：当订阅参数非法时立即得到稳定错误；合法时按既有主链路进入 subscribe/catchup。

断言：
1. 缺失 `series_id`、非法 `since`、非法 `supports_batch` 返回固定 bad_request payload；
2. 合法 payload 解析后能直接驱动 `handle_subscribe(...)`；
3. unsubscribe 的无效 `series_id` 保持兼容行为（静默忽略，不中断连接）。

## 验收命令与结果

- `pytest -q backend/tests/test_market_data_services.py backend/tests/test_market_data_contracts.py backend/tests/test_market_candles.py backend/tests/test_market_ws.py backend/tests/test_market_ws_disconnect_releases_ondemand.py backend/tests/test_e2e_user_story_market_sync.py`
- `cd frontend && npx tsc -b --pretty false --noEmit`
- `bash docs/scripts/doc_audit.sh`

## 回滚

- 单 commit 回滚：`git revert <sha>`
- 或回退以下文件：
  - `/Users/rick/code/trade_canvas/backend/app/market_data/services.py`
  - `/Users/rick/code/trade_canvas/backend/app/main.py`
