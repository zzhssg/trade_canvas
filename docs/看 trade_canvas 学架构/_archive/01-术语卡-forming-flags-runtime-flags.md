---
title: 术语卡：forming、flags、runtime flags 到底是什么
status: done
created: 2026-02-11
updated: 2026-02-11
---

# 术语卡：forming、flags、runtime flags 到底是什么

这篇只做一件事：把最容易混淆的三个词讲清楚。

---

## 1. `forming`：正在形成中的 K 线（临时态）

白话：`forming` 就是“这根 K 线还没收盘，还在变”。

在 trade_canvas 里，它的定位非常明确：

- 用于前端实时展示（让你看到蜡烛在跳）。
- 不进入因子计算主链路，不作为策略真源。
- 默认不落盘为历史真源（可广播，不做权威输入）。

为什么这样设计？  
因为 `forming` 天生会重绘，拿它做策略真源会导致“刚才有信号、现在没信号”的漂移。

口令版：**forming 可看，不可算。**

---

## 2. `flags`：功能开关（是否启用某能力）

白话：`flags` 就是“总闸刀”，决定功能开或关。

例如：

- `TRADE_CANVAS_ENABLE_FACTOR_INGEST`
- `TRADE_CANVAS_ENABLE_OVERLAY_INGEST`
- `TRADE_CANVAS_ENABLE_REPLAY_V1`

这些开关解决的是工程问题，不是业务问题：  
它让你能在不改代码的前提下，逐步放量、快速回滚、隔离风险。

口令版：**flags 决定功能生死。**

---

## 3. `runtime flags`：运行时参数快照（怎么跑）

白话：如果 `flags` 是“开不开”，`runtime flags` 就是“开了以后按什么参数跑”。

例如因子参数：

- `TRADE_CANVAS_PIVOT_WINDOW_MAJOR`
- `TRADE_CANVAS_FACTOR_LOOKBACK_CANDLES`
- `TRADE_CANVAS_FACTOR_STATE_REBUILD_EVENT_LIMIT`

这些会被加载成运行时配置对象，注入 orchestrator / service 使用。  
它们不只是布尔开关，还包括窗口大小、并发、限流等运行参数。

口令版：**runtime flags 决定运行口径。**

---

## 4. 三者关系（一句话）

- `forming`：数据形态（临时态）。
- `flags`：能力开关（是否启用）。
- `runtime flags`：运行口径（启用后如何执行）。

别混淆：  
`forming` 是“输入数据状态”，不是功能开关。  
`flags/runtime flags` 是“系统控制面”，不是业务数据本身。

---

## 5. 在本项目里的最小对照表

- 数据面：
  - `closed candle` -> 权威输入，进 factor/overlay 主链路
  - `forming candle` -> WS 展示友好，非权威

- 控制面：
  - `FeatureFlags` -> 基础布尔能力开关
  - `RuntimeFlags` -> 运行时综合配置（布尔 + 数值 + 字符串）

- 工程目标：
  - 可灰度
  - 可回滚
  - 可复现

---

## 6. 代码锚点

- `backend/app/derived_timeframes.py`（forming 语义注释）
- `backend/app/ingest_binance_ws.py`（forming 广播与节流）
- `backend/app/flags.py`（基础 flags 加载）
- `backend/app/runtime_flags.py`（runtime flags 汇总）
- `frontend/src/parts/ChartPanel.tsx`（`VITE_ENABLE_*` 示例）

---

## 7. 快速自测

1. 为什么 forming 不该参与 pen/zhongshu/anchor 计算？
2. 为什么同一个功能既需要开关也需要参数？
3. 如果线上异常，优先用哪种手段快速止损（改代码 or 关 flag）？

你如果能不看文档直接回答这三题，这三个术语就真的掌握了。
