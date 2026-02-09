---
title: Market Data 收口与模块化（Phase M：WS 错误 payload 统一构造）
status: done
owner: codex
created: 2026-02-09
updated: 2026-02-09
---

## 目标

- 统一 market WS 链路中的错误 payload 构造方式，减少字典硬编码与字段漂移风险。
- 保持现有对外错误语义（`bad_request/capacity`）不变。

## 变更范围

- 错误构造收口：
  - `/Users/rick/code/trade_canvas/backend/app/market_data/services.py`
  - 新增 `build_ws_error_payload(...)` 并让 parser/coordinator 复用。
- 导出统一能力：
  - `/Users/rick/code/trade_canvas/backend/app/market_data/__init__.py`
  - 导出 `build_ws_error_payload`。
- 回归测试：
  - `/Users/rick/code/trade_canvas/backend/tests/test_market_data_services.py`
  - 新增 `build_ws_error_payload` 的字段一致性测试（含可选 `series_id`）。

## E2E 用户故事（门禁）

Persona：交易员通过 WS 订阅市场数据，遇到非法参数或容量上限。  
Goal：服务端返回结构稳定的错误消息，客户端可按统一字段处理。

断言：
1. bad_request 错误结构固定为 `{type,error code,message}`；
2. capacity 错误在上述基础上包含 `series_id`；
3. parser 与 coordinator 发出的错误字段口径一致。

## 验收命令与结果

- `pytest -q backend/tests/test_market_data_services.py backend/tests/test_market_data_contracts.py backend/tests/test_market_candles.py backend/tests/test_market_ws.py backend/tests/test_market_ws_disconnect_releases_ondemand.py backend/tests/test_e2e_user_story_market_sync.py`（29 passed）
- `cd frontend && npx tsc -b --pretty false --noEmit`（pass）
- `bash docs/scripts/doc_audit.sh`（pass）

## 回滚

- 单 commit 回滚：`git revert <sha>`
- 或回退以下文件：
  - `/Users/rick/code/trade_canvas/backend/app/market_data/services.py`
  - `/Users/rick/code/trade_canvas/backend/app/market_data/__init__.py`
