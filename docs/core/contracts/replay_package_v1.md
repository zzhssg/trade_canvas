---
title: Replay Package Contract v1（复盘包：JSON 存储协议）
status: done
created: 2026-02-06
updated: 2026-02-15
---

# Replay Package Contract v1（复盘包：JSON 存储协议）

目标：定义 replay 包的落盘协议，保证同输入同输出、窗口化读取与 factor snapshot/draw 一致性。

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
    "idx_to_time": "windows[*].kline[idx].time",
    "factor_schema": []
  },
  "windows": [],
  "factor_snapshots": [],
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
- `metadata.factor_schema` 描述每个因子的 `history_keys/head_keys`。
- `factor_snapshots` 存储每个因子在每个 candle 的快照增量（仅内容变化时写入）。
- `window` 读取时对 `factor_snapshots` 自动合并“窗口内快照 + 窗口前最近基线快照”。

## 4) 重建规则

- 全量帧 `t`：
  1. `factor_snapshots` 过滤到 `candle_time <= t` 并按因子取最新快照
  2. 从对应 `window` 的 `catalog_* + checkpoints + diffs` 重建 draw active 集

## 5) 门禁

1. 对齐：`candle_id` 与 factor snapshot/draw 必须对齐同一 `candle_time`。
2. 可复现：同一输入多次 build，`cache_key` 与读取结果稳定一致。
3. 幂等：已有包时 `status=done`，不重复重建。
