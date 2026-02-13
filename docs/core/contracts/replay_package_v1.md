---
title: Replay Package Contract v1（复盘包：JSON 存储协议）
status: done
created: 2026-02-06
updated: 2026-02-13
---

# Replay Package Contract v1（复盘包：JSON 存储协议）

目标：定义 replay 包的落盘协议，保证同输入同输出、窗口化读取与 history/head/draw 一致性。

## 1) 存储介质与路径

- 介质：单文件 JSON（每个 `cache_key` 一份）。
- 路径：`backend/data/artifacts/replay_package_v1/<cache_key>/replay_package.json`。
- 只读访问不得触发重算；构建由显式 `build` 触发。

## 2) 顶层结构

```json
{
  "schema_version": 1,
  "cache_key": "string",
  "metadata": {
    "schema_version": 1,
    "series_id": "binance:futures:BTC/USDT:1m",
    "timeframe_s": 60,
    "total_candles": 100,
    "from_candle_time": 1700000000,
    "to_candle_time": 1700005940,
    "window_size": 50,
    "snapshot_interval": 5,
    "preload_offset": 0,
    "idx_to_time": "windows[*].kline[idx].time"
  },
  "windows": [],
  "history_events": [],
  "history_deltas": [],
  "factor_head_snapshots": [],
  "candle_store_head_time": 1700005940,
  "factor_store_last_event_id": 1234,
  "overlay_store_last_version_id": 5678,
  "created_at_ms": 1700006000123
}
```

## 3) 关键语义

- `windows[*]` 直接复用 overlay replay window 结构：
  - `window_index/start_idx/end_idx`
  - `kline`
  - `catalog_base/catalog_patch`
  - `checkpoints/diffs`
- `history_events` 是 append-only 事件序列。
- `history_deltas[idx]` 描述从上一个 idx 到当前 idx 的事件 id 区间。
- `factor_head_snapshots` 存储每根 K 的 head 快照（按 `factor_name/candle_time/seq`）。

## 4) 重建规则

- 全量帧 `t`：
  1. `history_events` 过滤到 `candle_time <= t`
  2. `factor_head_snapshots` 过滤到窗口时间范围并按 `seq` 选最新
  3. 从对应 `window` 的 `catalog_* + checkpoints + diffs` 重建 draw active 集
- 差值帧：
  - 以 `history_deltas` + window 内 `catalog_patch/diffs` 增量应用。

## 5) 门禁

1. 对齐：`candle_id` 与 history/head/draw 必须对齐同一 `candle_time`。
2. 可复现：同一输入多次 build，`cache_key` 与读取结果稳定一致。
3. 幂等：已有包时 `status=done`，不重复重建。

