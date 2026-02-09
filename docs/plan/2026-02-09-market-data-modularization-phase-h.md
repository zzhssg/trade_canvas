---
title: Market Data 收口与模块化（Phase H：断线清理协同收口）
status: done
owner: codex
created: 2026-02-09
updated: 2026-02-09
---

## 目标

- 把 WS finally 中断线清理逻辑（`hub.pop_ws` + ondemand refcount 释放）从 `main.py` 内联代码迁移到 `market_data`。
- 保持断线后释放行为不变，避免 refcount 泄漏。

## 变更范围

- 服务增强：
  - `/Users/rick/code/trade_canvas/backend/app/market_data/services.py`
  - `WsSubscriptionCoordinator.cleanup_disconnect(...)` 统一处理断线清理。
- 主链路接入：
  - `/Users/rick/code/trade_canvas/backend/app/main.py`
  - finally 中改为单点调用 coordinator cleanup。
- 回归测试：
  - `/Users/rick/code/trade_canvas/backend/tests/test_market_data_services.py`
  - 覆盖 cleanup 路径（含 hub.pop_ws 返回集合合并）。

## E2E 用户故事（门禁）

Persona：交易员在订阅多个 series 后突然断开 WS。  
Goal：服务端应释放 hub 中的 ws 订阅记录，并释放对应 ondemand ingest refcount，避免僵尸任务。

断言：
1. finally 必须调用 cleanup；
2. cleanup 释放 `subscribed_series ∪ hub.pop_ws` 的 series；
3. 任一 series 释放失败不影响其他 series 的释放（best-effort）。

## 验收命令与结果

- `pytest -q backend/tests/test_market_data_services.py backend/tests/test_market_data_contracts.py backend/tests/test_market_candles.py backend/tests/test_market_ws.py backend/tests/test_market_ws_disconnect_releases_ondemand.py backend/tests/test_e2e_user_story_market_sync.py`
- `cd frontend && npx tsc -b --pretty false --noEmit`
- `bash docs/scripts/doc_audit.sh`

## 回滚

- 单 commit 回滚：`git revert <sha>`
- 或回退 `/Users/rick/code/trade_canvas/backend/app/main.py` finally 对 `cleanup_disconnect(...)` 的调用，恢复原内联逻辑。
