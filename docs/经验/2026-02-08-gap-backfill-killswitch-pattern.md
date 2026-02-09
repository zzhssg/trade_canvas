---
title: 经验：市场 gap 回补采用“公共能力 + kill-switch + 回归测试”模式
status: done
created: 2026-02-08
updated: 2026-02-08
---

# 经验：市场 gap 回补采用“公共能力 + kill-switch + 回归测试”模式

## 场景与目标

场景：WS 订阅 catchup 发现 `expected_next_time < actual_time`，图表出现时间缺口。  
目标：在不破坏现有协议兼容性的前提下，先补齐缺口，再决定是否下发 `gap`。

## 做对了什么

- 抽出公共回补模块：`backend/app/market_backfill.py`，让 replay 与 market realtime 复用同一套 CCXT 回补能力。  
- 引入后端开关：`TRADE_CANVAS_ENABLE_MARKET_GAP_BACKFILL`（默认 `0`），实现灰度放量与快速回滚。  
- 先补测试再收口：新增 `backend/tests/test_market_ws.py::test_ws_subscribe_gap_backfill_enabled_rehydrates_missing_candles` 保证行为可回归。  
- 同步文档：更新 `docs/core/market-kline-sync.md` 与 `docs/core/api/v1/ws_market.md`，保证契约与实现一致。

## 为什么有效

- 公共能力减少重复代码，避免 replay/market 各自演化后口径漂移。  
- kill-switch 让高风险行为具备“秒级降级”能力，避免上线后只能改代码回滚。  
- 回归测试把“补齐成功才不发 gap”的预期固定为机器可验证规则。

## 复用方式（下次怎么做）

- 任何“主链路新增自动行为”默认都加 `TRADE_CANVAS_ENABLE_*` 开关（默认关闭）。  
- 发现同类能力散落在多个模块时，优先抽公共模块并在两个调用方同时切换。  
- 至少补 1 条“会失败的”路径测试，再补 happy path。  
- 交付前固定执行：
  - `pytest -q`
  - `bash docs/scripts/doc_audit.sh`

## 关联与证据

- 代码路径：
  - `backend/app/market_backfill.py`
  - `backend/app/main.py`
  - `backend/app/replay_package_service_v1.py`
  - `backend/tests/test_market_ws.py`
- 文档路径：
  - `docs/core/market-kline-sync.md`
  - `docs/core/api/v1/ws_market.md`
