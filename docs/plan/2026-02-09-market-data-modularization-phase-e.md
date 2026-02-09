---
title: Market Data 收口与模块化（Phase E：WS Catchup 协调收口）
status: done
owner: codex
created: 2026-02-09
updated: 2026-02-09
---

## 目标

- 把 WS subscribe 流程中 `since / last_sent / catchup / gap-heal` 的协调逻辑从 `main.py` 移入 `market_data`。
- 保持 WS 对外行为不变（尤其是 gap race 场景不重复推送）。

## 变更范围

- 契约扩展：
  - `/Users/rick/code/trade_canvas/backend/app/market_data/contracts.py`
  - 新增 `WsCatchupRequest`，并在 orchestrator 增加 `build_ws_catchup(...)`。
- 服务实现：
  - `/Users/rick/code/trade_canvas/backend/app/market_data/services.py`
  - `DefaultMarketDataOrchestrator.build_ws_catchup(...)` 统一处理过滤与 heal。
- 主链路接入：
  - `/Users/rick/code/trade_canvas/backend/app/main.py`
  - WS subscribe 先 read，再获取 `last_sent`，最后调用 orchestrator 汇总结果。
- 测试：
  - `/Users/rick/code/trade_canvas/backend/tests/test_market_data_services.py`
  - `/Users/rick/code/trade_canvas/backend/tests/test_market_data_contracts.py`

## E2E 用户故事（门禁）

Persona：交易员在 `1m` 图订阅过程中，恰逢 live candle 到达与 catchup 并发。  
Goal：服务端仅输出一份有效 `candle_closed`，不重复；若存在缺口仍先按策略回补或发送 `gap`。

断言：
1. `since` 与 `last_sent` 协调后只保留 `> effective_since` 的 catchup；
2. gap-heal 仍在统一服务中执行；
3. 既有 `test_ws_gap_race_does_not_duplicate` 通过。

## 验收命令与结果

- `pytest -q backend/tests/test_market_data_services.py backend/tests/test_market_data_contracts.py backend/tests/test_market_candles.py backend/tests/test_market_ws.py backend/tests/test_e2e_user_story_market_sync.py`
- `cd frontend && npx tsc -b --pretty false --noEmit`
- `bash docs/scripts/doc_audit.sh`

## 回滚

- 单 commit 回滚：`git revert <sha>`
- 或回退 `/Users/rick/code/trade_canvas/backend/app/main.py` WS subscribe 中对 `build_ws_catchup(...)` 的接入。
