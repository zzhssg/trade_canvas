---
title: BTC 实时 K 线（Binance 1m WS → 多周期派生 + 收盘事件）
status: 已上线
created: 2026-02-07
updated: 2026-02-07
---

# BTC 实时 K 线（Binance 1m WS → 多周期派生 + 收盘事件）

目标：仅连接 `binance:futures:BTC/USDT:1m` 的 websocket（单一上游实时源），在服务端对 `1m/5m/15m/1h/4h/1d` 做二次加工：

- 所有周期都能展示实时价格跳动（`forming` 只走 WS，不落库）
- 所有周期都能正确产出收盘事件（`closed` 落库 + 触发因子/overlay 计算）
- 对外契约保持稳定：复用现有 `GET /api/market/candles` 与 `WS /ws/market`

## 范围 / 非范围

- 范围：`binance:futures:BTC/USDT`；timeframes 固定为 `["1m","5m","15m","1h","4h","1d"]`
- 非范围：非 BTC、非 futures、非 Binance；forming 入库；新增前端交互/新增 endpoint

## 开关（Kill-switch）

- `TRADE_CANVAS_ENABLE_DERIVED_TIMEFRAMES=1`：启用“从 1m 派生多周期”
- `TRADE_CANVAS_DERIVED_BASE_TIMEFRAME=1m`：基准周期（本期固定）
- `TRADE_CANVAS_DERIVED_TIMEFRAMES=5m,15m,1h,4h,1d`：派生周期集合

默认均为关闭（`0`/空值表示关闭），确保可回滚。

## 关键不变量（必须保持）

- **closed candle 为权威输入**：forming 仅用于展示，不进因子、不落库
- 稳定主键：`candle_id = "{series_id}:{candle_time}"`
- 幂等：重复写入同一 `(series_id, candle_time)` 必须安全（upsert）
- 对外单调：WS/HTTP 输出以 `candle_time` 为主键合并；发现缺口必须显式 gap

## E2E 用户故事（门禁）

Persona：交易员在前端查看 BTC 行情。  
Goal：切换到任意周期（例如 5m）仍可见实时跳动，并且每次收盘后产生可查询的闭合 K（并触发因子/overlay 链路）。

步骤与断言（可执行）：

1) 启动后端（单一上游 WS + 派生开启）：

```bash
TRADE_CANVAS_MARKET_REALTIME_SOURCE=binance_ws \
TRADE_CANVAS_ENABLE_WHITELIST_INGEST=1 \
TRADE_CANVAS_ENABLE_DERIVED_TIMEFRAMES=1 \
uvicorn backend.app.main:create_app --factory --port 18080
```

2) 订阅 5m（WS）并断言收到 forming（至少 1 条）与 closed（至少 1 条）：

```bash
wscat -c ws://127.0.0.1:18080/ws/market \
  -x '{"type":"subscribe","series_id":"binance:futures:BTC/USDT:5m","since":null,"supports_batch":true}'
```

断言：
- 出现 `{"type":"candle_forming","series_id":"...:5m",...}`
- 出现 `{"type":"candle_closed","series_id":"...:5m",...}` 或 `candles_batch` 里包含 5m
- 且 `candle.candle_time % 300 == 0`

3) 通过 HTTP 查询 5m 最新闭合 K 已落库：

```bash
curl -s 'http://127.0.0.1:18080/api/market/candles?series_id=binance:futures:BTC/USDT:5m&limit=10' | jq .
```

断言：
- 返回 `candles` 非空
- 最后一根 `candles[-1].candle_time` 与 WS 收到的 5m close 时间一致

## 里程碑拆解（小步可回滚）

### M0：派生 closed（落库 + 因子/overlay ingest + WS 广播）

- 改什么：
  - 新增派生聚合组件（DerivedTimeframeFanout）
  - 在 Binance 1m WS ingest finalized flush 路径中生成派生 closed，并写入 SQLite
  - 对派生 series_id 触发 `FactorOrchestrator.ingest_closed()` / `OverlayOrchestrator.ingest_closed()`
  - 通过 `CandleHub.publish_closed_batch()` 对派生 series_id 广播
- 验收：
  - `python3 -m pytest backend/tests/test_ingest_binance_ws.py -q`
  - `python3 -m pytest backend/tests/test_derived_timeframes.py -q`
- 回滚：
  - 关闭 `TRADE_CANVAS_ENABLE_DERIVED_TIMEFRAMES`
  - 或 `git revert` 对应 commit

### M1：派生 forming（只走 WS，不落库）

- 改什么：
  - 在 Binance WS ingest 的 forming 分支中生成派生 forming，并 WS 广播
  - 对派生 forming 做节流（与现有 `TRADE_CANVAS_MARKET_FORMING_MIN_INTERVAL_MS` 对齐）
- 验收：
  - `python3 -m pytest backend/tests/test_derived_timeframes.py -q`
- 回滚：
  - 关闭开关或 revert

### M2：订阅收敛（订阅派生周期不再启动上游 job）

- 改什么：
  - supervisor：订阅 `...:5m/15m/1h/4h/1d` 时映射到 base `...:1m` 管理 refcount/job
- 验收：
  - `python3 -m pytest backend/tests/test_ingest_supervisor_capacity.py -q`
- 回滚：
  - 关闭开关或 revert

