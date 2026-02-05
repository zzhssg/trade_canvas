---
title: API v1 · Overlay（HTTP）
status: deprecated
created: 2026-02-03
updated: 2026-02-05
---

# API v1 · Overlay（HTTP）

说明：`/api/overlay/delta` 为历史遗留接口，已于 2026-02-05 **彻底移除**；新代码统一使用 `GET /api/draw/delta`。

## 已移除：GET /api/overlay/delta

> Removed：旧接口已删除；请改用 `GET /api/draw/delta`。

### 示例（curl）

```bash
curl --noproxy '*' -sS \
  "http://127.0.0.1:8000/api/overlay/delta?series_id=binance:futures:BTC/USDT:1m&cursor_version_id=0&window_candles=2000"
```

### 示例响应（json）

```json
{
  "schema_version": 1,
  "series_id": "binance:futures:BTC/USDT:1m",
  "to_candle_id": "binance:futures:BTC/USDT:1m:1700000000",
  "to_candle_time": 1700000000,
  "active_ids": ["pivot.major:1700000000:resistance:2"],
  "instruction_catalog_patch": [
    {
      "version_id": 1,
      "instruction_id": "pivot.major:1700000000:resistance:2",
      "kind": "marker",
      "visible_time": 1700000000,
      "definition": {
        "type": "marker",
        "feature": "pivot.major",
        "time": 1700000000,
        "position": "aboveBar",
        "color": "#ef4444",
        "shape": "circle",
        "text": ""
      }
    }
  ],
  "next_cursor": {"version_id": 1}
}
```

### 语义

- `cursor_version_id` 是 overlay store 的增量游标：服务端返回 `instruction_catalog_patch`（从 after_version_id 之后到当前 head 的变更）。
- `active_ids` 是当前窗口内应渲染的指令 id 列表（服务端会按窗口裁剪并排序）。
- 如 overlay store 尚未构建到可对齐时间，部分点查/回放语义会走 fail-safe（相关约束见 `GET /api/draw/delta` 的 `at_time` 行为）。
