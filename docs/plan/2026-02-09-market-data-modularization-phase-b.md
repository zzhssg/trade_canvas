---
title: Market Data 收口与模块化（Phase B：读取与新鲜度迁移）
status: done
owner: codex
created: 2026-02-09
updated: 2026-02-09
---

## 目标

- 在不改变 HTTP/WS 外部协议的前提下，把市场 K 线读取与 catchup gap-heal 调度收口到 `market_data` 域服务。
- 路由层只保留参数校验和协议编解码，读取/新鲜度口径统一由 orchestrator 提供。

## 变更范围

- 新增 `backend/app/market_data/services.py`
  - `StoreCandleReadService`
  - `StoreFreshnessService`
  - `HubWsDeliveryService`
  - `DefaultMarketDataOrchestrator`
- 修改 `backend/app/main.py`
  - `GET /api/market/candles` 改为调用 `MarketDataOrchestrator.read_candles`
  - `WS subscribe` 的 catchup 读取与 heal 调度改为调用 `MarketDataOrchestrator`
- 新增 `backend/tests/test_market_data_services.py` 验证读链路与新鲜度分类。

## E2E 用户故事（门禁）

Persona：交易员打开 `binance:futures:BTC/USDT:1m` 图表并持续订阅。  
Goal：先拿到 HTTP tail，再在 WS 中收到 catchup/live；遇到 gap 时先走 best-effort heal，再决定是否发 `gap`。

断言：
1. `GET /api/market/candles?limit=2` 仍返回升序 tail 与正确 `server_head_time`。
2. `GET /api/market/candles?since=160` 仍保持 `> since` 语义。
3. `WS subscribe` 仍可收到 catchup + live，且 gap-heal 路径可用。

## 验收命令与结果

- `pytest -q backend/tests/test_market_data_services.py`
- `pytest -q backend/tests/test_market_candles.py backend/tests/test_market_ws.py backend/tests/test_e2e_user_story_market_sync.py`
- `bash docs/scripts/doc_audit.sh`

## 回滚

- 单 commit 可回滚：`git revert <sha>`
- 或仅回退 `backend/app/main.py` 对 orchestrator 的接入，恢复直接调用 `store/hub`。
