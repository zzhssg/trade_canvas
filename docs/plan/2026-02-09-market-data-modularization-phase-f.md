---
title: Market Data 收口与模块化（Phase F：WS Catchup 发包收口）
status: done
owner: codex
created: 2026-02-09
updated: 2026-02-09
---

## 目标

- 把 WS subscribe 的 catchup 发包策略（`gap` + `candles_batch/candle_closed`）从 `main.py` 移入 `market_data`。
- 保持消息结构和顺序兼容，不影响既有客户端与 E2E 用户故事。

## 变更范围

- 契约扩展：
  - `/Users/rick/code/trade_canvas/backend/app/market_data/contracts.py`
  - 新增 `WsEmitRequest` / `WsEmitResult`，orchestrator 新增 `build_ws_emit(...)`。
- 服务实现：
  - `/Users/rick/code/trade_canvas/backend/app/market_data/services.py`
  - 统一组装 WS payload（batch/single）与 `last_sent_time`。
- 主链路接入：
  - `/Users/rick/code/trade_canvas/backend/app/main.py`
  - 路由层不再内联分支拼包，只循环发送 payload 并一次性更新 last_sent。
- 测试：
  - `/Users/rick/code/trade_canvas/backend/tests/test_market_data_services.py`
  - `/Users/rick/code/trade_canvas/backend/tests/test_market_data_contracts.py`

## E2E 用户故事（门禁）

Persona：交易员订阅 `1m` 图，在 catchup 阶段既要看到 gap 信号，也要看到 batch/single 的闭合 K。  
Goal：无论客户端是否支持 batch，服务端都按同一策略输出 payload，不重复、不乱序。

断言：
1. single 路径输出顺序：`gap`（可选）→ `candle_closed...`；
2. batch 路径输出顺序：`gap`（可选）→ `candles_batch`；
3. `test_ws_gap_race_does_not_duplicate` 继续通过。

## 验收命令与结果

- `pytest -q backend/tests/test_market_data_services.py backend/tests/test_market_data_contracts.py backend/tests/test_market_candles.py backend/tests/test_market_ws.py backend/tests/test_e2e_user_story_market_sync.py`
- `cd frontend && npx tsc -b --pretty false --noEmit`
- `bash docs/scripts/doc_audit.sh`

## 回滚

- 单 commit 回滚：`git revert <sha>`
- 或回退 `/Users/rick/code/trade_canvas/backend/app/main.py` 对 `build_ws_emit(...)` 的接入，恢复路由层内联发包。
