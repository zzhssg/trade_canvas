---
title: API v1 · Draw（HTTP）
status: draft
created: 2026-02-03
updated: 2026-02-03
---

# API v1 · Draw（HTTP）

## GET /api/draw/delta

### 示例（curl）

```bash
curl --noproxy '*' -sS \
  "http://127.0.0.1:8000/api/draw/delta?series_id=binance:futures:BTC/USDT:1m&cursor_version_id=0&window_candles=2000"
```

### 示例响应（json）

```json
{
  "schema_version": 1,
  "series_id": "binance:futures:BTC/USDT:1m",
  "to_candle_id": "binance:futures:BTC/USDT:1m:1700000000",
  "to_candle_time": 1700000000,
  "active_ids": ["pivot:1700000000"],
  "instruction_catalog_patch": [
    {
      "version_id": 1,
      "instruction_id": "pivot:1700000000",
      "kind": "marker",
      "visible_time": 1700000000,
      "definition": {"time": 1700000000, "text": "pivot", "color": "#ef4444"}
    }
  ],
  "series_points": {},
  "next_cursor": {"version_id": 1, "point_time": null}
}
```

### 语义

- draw/delta 是统一绘图增量输出（v1 base）：
  - overlay 指令：`instruction_catalog_patch + active_ids`
  - 指标线点：`series_points`（当前实现先返回空，后续版本会落地）
- `at_time`（可选）用于回放点查上界：服务端会先将其 floor 到 closed candle 的对齐时间。
- fail-safe：当 `at_time` 给定但 overlay store 的 head 尚未追到该对齐时间时，返回 `409 ledger_out_of_sync:overlay`，禁止“声称对齐但实际没追上”的漂移。

