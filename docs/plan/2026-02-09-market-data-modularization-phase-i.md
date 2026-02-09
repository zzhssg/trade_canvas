---
title: Market Data 收口与模块化（Phase I：订阅状态本地化）
status: done
owner: codex
created: 2026-02-09
updated: 2026-02-09
---

## 目标

- 把 WS 路由内的 `subscribed_series` 本地状态迁移到 `WsSubscriptionCoordinator` 内部维护。
- 保持断线 cleanup 行为不变，并减少路由函数形参/局部状态复杂度。

## 变更范围

- 服务增强：
  - `/Users/rick/code/trade_canvas/backend/app/market_data/services.py`
  - `WsSubscriptionCoordinator` 新增本地状态管理（remember/forget/pop_local）。
- 主链路接入：
  - `/Users/rick/code/trade_canvas/backend/app/main.py`
  - 移除 `subscribed_series` 列表，finally cleanup 不再传列表参数。
- 回归测试：
  - `/Users/rick/code/trade_canvas/backend/tests/test_market_data_services.py`
  - 覆盖本地状态 + hub.pop_ws 的合并释放。

## E2E 用户故事（门禁）

Persona：交易员订阅多个 series，并在部分退订后断开连接。  
Goal：系统只释放“仍处于订阅态”的 series（加上 hub 的残留记录），避免遗漏或重复释放。

断言：
1. subscribe 成功后会记录本地订阅状态；
2. unsubscribe 后会移除本地状态；
3. cleanup 按 `local_state ∪ hub.pop_ws` 释放 ondemand 订阅。

## 验收命令与结果

- `pytest -q backend/tests/test_market_data_services.py backend/tests/test_market_data_contracts.py backend/tests/test_market_candles.py backend/tests/test_market_ws.py backend/tests/test_market_ws_disconnect_releases_ondemand.py backend/tests/test_e2e_user_story_market_sync.py`
- `cd frontend && npx tsc -b --pretty false --noEmit`
- `bash docs/scripts/doc_audit.sh`

## 回滚

- 单 commit 回滚：`git revert <sha>`
- 或回退 `/Users/rick/code/trade_canvas/backend/app/main.py`，恢复 `subscribed_series` 路由本地管理模式。
