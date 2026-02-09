---
title: Market Data 收口与模块化（Phase G：订阅协同收口）
status: done
owner: codex
created: 2026-02-09
updated: 2026-02-09
---

## 目标

- 把 WS subscribe/unsubscribe 中的 ondemand ingest 与 hub 协同逻辑从 `main.py` 抽到 `market_data`。
- 保持 capacity 拒绝语义、错误结构和现有测试行为不变。

## 变更范围

- 服务新增：
  - `/Users/rick/code/trade_canvas/backend/app/market_data/services.py`
  - 新增 `WsSubscriptionCoordinator`，统一处理 subscribe/unsubscribe 协同。
- 主链路接入：
  - `/Users/rick/code/trade_canvas/backend/app/main.py`
  - WS subscribe/unsubscribe 改为调用 coordinator，不再手写容量错误 payload。
- 导出更新：
  - `/Users/rick/code/trade_canvas/backend/app/market_data/__init__.py`
- 回归测试：
  - `/Users/rick/code/trade_canvas/backend/tests/test_market_data_services.py`
  - 新增 coordinator 的容量拒绝/退订协同测试。

## E2E 用户故事（门禁）

Persona：交易员同时订阅多个交易对，命中 ondemand job 容量上限。  
Goal：服务端返回标准 `capacity` 错误，不应发送 catchup；退订后应释放对应 refcount，并解除 hub 订阅。

断言：
1. capacity 拒绝时 payload 保持 `{type:error, code:capacity, message:ondemand_ingest_capacity, series_id}`；
2. 订阅成功时必须先完成 ondemand 订阅，再执行 hub 订阅；
3. 退订时 ondemand 与 hub 都被调用。

## 验收命令与结果

- `pytest -q backend/tests/test_market_data_services.py backend/tests/test_market_data_contracts.py backend/tests/test_market_candles.py backend/tests/test_market_ws.py backend/tests/test_e2e_user_story_market_sync.py`
- `cd frontend && npx tsc -b --pretty false --noEmit`
- `bash docs/scripts/doc_audit.sh`

## 回滚

- 单 commit 回滚：`git revert <sha>`
- 或回退 `/Users/rick/code/trade_canvas/backend/app/main.py` 对 `WsSubscriptionCoordinator` 的接入，恢复原有 subscribe/unsubscribe 内联逻辑。
