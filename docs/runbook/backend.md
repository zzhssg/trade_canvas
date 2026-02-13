---
title: Backend 运行手册（market kline sync API）
status: draft
created: 2026-02-02
updated: 2026-02-13
---

# Backend 运行手册（market kline sync API）

## 启动

```bash
bash scripts/dev_backend.sh
```

Whitelist 真源：`backend/config/market_whitelist.json`。

### ingest 运行模式（单一 realtime：binance_ws）

```bash
export TRADE_CANVAS_ENABLE_WHITELIST_INGEST=1
export TRADE_CANVAS_ENABLE_ONDEMAND_INGEST=1  # 默认已开启（dev_backend.sh）
export TRADE_CANVAS_ONDEMAND_IDLE_TTL_S=60
export TRADE_CANVAS_ONDEMAND_MAX_JOBS=8  # 避免同时订阅过多标的导致本机卡顿
export TRADE_CANVAS_ENABLE_PG_STORE=1
export TRADE_CANVAS_POSTGRES_DSN='postgresql://tc:tc@127.0.0.1:5432/trade_canvas'
export TRADE_CANVAS_POSTGRES_SCHEMA=trade_canvas
bash scripts/dev_backend.sh
```

说明：
- realtime ingest 仅使用 Binance WS（`binance_ws`）；不再提供 `ccxt|binance_ws` 二选一模式。
- 当 `TRADE_CANVAS_ENABLE_WHITELIST_INGEST=0` 时，白名单币种在被前端订阅后会自动回退到 ondemand ingest（避免“默认币种不跳动”）。

## 回测（freqtrade backtesting）

回测依赖 freqtrade 与可用的历史数据（datadir）。后端会基于 `TRADE_CANVAS_FREQTRADE_CONFIG` 生成一份“最小回测临时 config”，并调用子进程执行。

常用环境变量：
- `TRADE_CANVAS_FREQTRADE_ROOT`：freqtrade 工作目录（用于相对路径与 PYTHONPATH 注入）
- `TRADE_CANVAS_FREQTRADE_CONFIG`：base config 路径
- `TRADE_CANVAS_FREQTRADE_USERDIR`：可选，透传给 `freqtrade --userdir`
- `TRADE_CANVAS_FREQTRADE_BIN`：可选，默认 `freqtrade`
- `TRADE_CANVAS_FREQTRADE_STRATEGY_PATH`：可选，默认 `./Strategy`（透传给 `freqtrade --strategy-path`）
- `TRADE_CANVAS_FREQTRADE_OFFLINE_MARKETS`：可选，值为 `1` 时启用离线 markets 注入（避免 backtesting 启动阶段访问交易所 exchangeInfo）
- `TRADE_CANVAS_BACKTEST_REQUIRE_TRADES`：可选，值为 `1` 时要求回测必须产出 trades（否则 422）
- `TRADE_CANVAS_CORS_ORIGINS`：允许前端跨端口访问（默认已包含 `localhost:5173`）

列出策略：

```bash
curl --noproxy '*' -sS "http://127.0.0.1:8000/api/backtest/strategies"
```

运行回测（示例）：

```bash
curl --noproxy '*' -sS -X POST "http://127.0.0.1:8000/api/backtest/run" \
  -H 'content-type: application/json' \
  -d '{"strategy_name":"TradeCanvasAlwaysTradeSpotStrategy","pair":"BTC/USDT","timeframe":"1m","timerange":"20260130-20260201"}'
```

## 写入（显式 ingest，用于本地验证）

```bash
curl --noproxy '*' -sS -X POST "http://127.0.0.1:8000/api/market/ingest/candle_closed" \
  -H 'content-type: application/json' \
  -d '{"series_id":"binance:futures:BTC/USDT:1m","candle":{"candle_time":100,"open":1,"high":2,"low":0.5,"close":1.5,"volume":10}}'
```

## 因子指纹自动重算（默认开启）

用于避免“代码口径已变，但历史 factor 事件仍是旧口径”的数据漂移。

行为：
- 后端在 factor ingest 时计算当前逻辑指纹（核心代码哈希 + 关键参数）。
- 当检测到同一 `series_id` 指纹变化时，自动删除旧数据并仅保留最近 2000 根 K 线（可由 `TRADE_CANVAS_FACTOR_REBUILD_KEEP_CANDLES` 覆盖），再基于这批“新数据”重算 factor/overlay。
- 重算完成后通过市场 WS 推送一条系统消息（`type=system,event=factor.rebuild`），前端显示 toast 提示即可。

可选开关：
- `TRADE_CANVAS_ENABLE_FACTOR_FINGERPRINT_REBUILD`：默认 `1`，可临时设为 `0` 关闭自动重算。
- `TRADE_CANVAS_FACTOR_REBUILD_KEEP_CANDLES`：默认 `2000`，重算前保留的最新 K 线数量。
- `TRADE_CANVAS_FACTOR_LOGIC_VERSION`：可选版本闸，用于人工触发一次口径升级重算。

## 读取（HTTP 增量）

```bash
curl --noproxy '*' -sS "http://127.0.0.1:8000/api/market/candles?series_id=binance:futures:BTC/USDT:1m&since=0&limit=500"
```

## 市场列表（Top20）

后端统一代理（避免前端直连交易所/CORS/口径漂移）：

```bash
curl --noproxy '*' -sS "http://127.0.0.1:8000/api/market/top_markets?exchange=binance&market=spot&quote_asset=USDT&limit=20"
curl --noproxy '*' -sS "http://127.0.0.1:8000/api/market/top_markets?exchange=binance&market=futures&quote_asset=USDT&limit=20"
```

可选：强制刷新（有频率限制，可能返回 429）：

```bash
curl --noproxy '*' -sS "http://127.0.0.1:8000/api/market/top_markets?exchange=binance&market=spot&force=1"
```

可选环境变量（默认值见代码）：
- `TRADE_CANVAS_BINANCE_SPOT_BASE_URL`
- `TRADE_CANVAS_BINANCE_FUTURES_BASE_URL`
- `TRADE_CANVAS_BINANCE_EXCHANGEINFO_TTL_S`
- `TRADE_CANVAS_BINANCE_TICKER_TTL_S`

### SSE 推送（可选）

```bash
curl --noproxy '*' -N "http://127.0.0.1:8000/api/market/top_markets/stream?exchange=binance&market=spot&quote_asset=USDT&limit=20"
```

## WS（订阅）

任意 WS 客户端向 `ws://127.0.0.1:8000/ws/market` 连接后发送：

```json
{"type":"subscribe","series_id":"binance:futures:BTC/USDT:1m","since":100}
```

## Troubleshooting：curl 访问 localhost 卡住

如果你的环境设置了 `http_proxy/https_proxy`（常见于 Clash / Surge / 其他代理工具），`curl` 可能会把 `localhost/127.0.0.1` 也走代理，表现为请求卡住或超时。

- 推荐：统一用 `127.0.0.1` 并加 `--noproxy '*'`（本手册已按此写法）
- 或设置（一次性或写进 shell 配置）：

```bash
export NO_PROXY="localhost,127.0.0.1,::1"
export no_proxy="$NO_PROXY"
```
