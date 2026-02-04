---
title: WS candles_batch（实盘 fresh-db 首屏批量下发）
status: draft
created: 2026-02-03
updated: 2026-02-03
---

# WS candles_batch（实盘 fresh-db 首屏批量下发）

目标：当使用 `bash scripts/dev_backend.sh --fresh-db` 启动后端时，前端图表首次打开不再“逐根冒出来”，而是通过 WS 一次性批量下发 catchup（最近窗口），之后仅在新 K 线收线后增量 +1 根。

## E2E 用户故事（门禁）

- Persona：研究者（打开图表看实时/近历史）
- Goal：fresh-db 下首屏一次性出现最近 2000 根，之后每次收线只增量一根

### 步骤与断言

1) 启动后端（fresh-db）
   - 命令：`bash scripts/dev_backend.sh --fresh-db`
2) 打开前端图表页，订阅任意 `series_id`（例如 `binance:futures:BTC/USDT:1m`）
3) 断言：WS 首条 catchup 为批量消息
   - 断言：收到 `type=candles_batch`，且 `candles.length > 0`
4) 断言：后续实时仍为单根增量
   - 动作：继续等待一根新收线
   - 断言：收到 `type=candle_closed`（单根），且 `candle.candle_time` 严格递增

### 证据与产物

- 后端单测：`pytest -q`
- 前端构建：`cd frontend && npm run build`
- 关键日志：`output/`（如需要再补充）

## 回滚方案

- 前端：取消 subscribe 的 `supports_batch`（立即回退到旧逐根行为）
- 后端：保持对旧客户端的 `candle_closed` 逐条推送兼容（无需回滚 DB）

