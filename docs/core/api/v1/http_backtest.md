---
title: API v1 · Backtest（HTTP）
status: done
created: 2026-02-03
updated: 2026-02-11
---

# API v1 · Backtest（HTTP）

> 说明：后端可能运行在 mock 模式（`TRADE_CANVAS_FREQTRADE_MOCK=1`），此时返回的策略/回测结果是用于联调的固定输出。

## GET /api/backtest/strategies

### 示例（curl）

```bash
curl --noproxy '*' -sS "http://127.0.0.1:8000/api/backtest/strategies?recursive=true"
```

### 示例响应（json）

```json
{"strategies": ["DemoStrategy"]}
```

### 语义

- 返回可用策略名列表（真实模式下读取 `Strategy/` 或 freqtrade userdir；mock 模式固定返回 `DemoStrategy`）。

## GET /api/backtest/pair_timeframes

### 示例（curl）

```bash
curl --noproxy '*' -sS \
  "http://127.0.0.1:8000/api/backtest/pair_timeframes?pair=BTC/USDT"
```

### 示例响应（json）

```json
{
  "pair": "BTC/USDT",
  "trading_mode": "mock",
  "datadir": "",
  "available_timeframes": []
}
```

### 语义

- 返回该交易对在 datadir 中可用的 timeframe 列表（用于 UI 下拉与“无数据时提示 download-data”）。
- futures 模式下会做 pair 归一化（例如 `BTC/USDT` 可能补成 `BTC/USDT:USDT`），以匹配 freqtrade 的历史路径规则。

## POST /api/backtest/run

### 示例请求（curl）

```bash
curl --noproxy '*' -sS -X POST "http://127.0.0.1:8000/api/backtest/run" \
  -H 'content-type: application/json' \
  -d '{"strategy_name":"DemoStrategy","pair":"BTC/USDT","timeframe":"1h","timerange":"20260130-20260201"}'
```

### 示例请求体（json）

```json
{
  "strategy_name": "DemoStrategy",
  "pair": "BTC/USDT",
  "timeframe": "1h",
  "timerange": "20260130-20260201"
}
```

### 示例响应（json）

```json
{
  "ok": true,
  "exit_code": 0,
  "duration_ms": 1,
  "command": ["freqtrade", "backtesting", "--strategy", "DemoStrategy", "--timeframe", "1h", "--pairs", "BTC/USDT", "--timerange", "20260130-20260201"],
  "stdout": "TRADE_CANVAS MOCK BACKTEST\nstrategy=DemoStrategy\npair=BTC/USDT\ntimeframe=1h\ntimerange=20260130-20260201\nresult=ok",
  "stderr": ""
}
```

### 语义

- `strategy_name` 会做白名单式校验（非法字符直接 400）。
- 若历史数据缺失，真实模式可能返回 422，并附带 `download_data_cmd` 提示如何补数据。

