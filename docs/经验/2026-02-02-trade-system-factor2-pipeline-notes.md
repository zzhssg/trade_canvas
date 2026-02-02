---
title: trade_system factor2 pipeline notes (for trade_canvas critical inheritance)
status: draft
created: 2026-02-02
updated: 2026-02-02
---

# trade_system factor2 pipeline notes (for trade_canvas critical inheritance)

目标：回答“trade_system 是怎么从消费 K 线 → 产出数据 → 冷热存储 → 事件驱动 → 绘图”的，并提取 **可继承的不变量/契约**（不抄实现负债）。

> 结论以 trade_system 的文档/代码为准；本笔记仅做“导航 + 语义摘要”。

## 1) 总览：一条 finalized K 线驱动三类产物

trade_system 的核心设计是把所有下游（overlay/replay/live-delta/解释）收敛到“同源底座 + 派生产物”：

- **权威输入**：`closed/finalized candle`（forming 不进入因子引擎）。
- **同源底座（Canonical）**：
  - `Factor Ledger`：唯一的 snapshots source（`history(t)+head(t)`），主键是 `candle_time`（Unix seconds）。
  - `SlotDelta Ledger`：二级同源底座，持久化绘图增量（slot diff + instruction_catalog_patch），供 replay/live/overlay 共用。
- **派生产物（Artifacts，可丢弃可重建）**：overlay bundle、replay-package、query-view、explain 等。

权威文档入口：
- `../trade_system/user_data/doc/Core/ARCHITECTURE.md`
- `../trade_system/user_data/doc/Core/【SAD】Computed Artifacts Service 终局架构（Ledger-SlotDelta）.md`
- `../trade_system/user_data/doc/Core/Contracts/factor_ledger_v1.md`
- `../trade_system/user_data/doc/Core/Contracts/slot_delta_ledger_v1.md`
- `../trade_system/user_data/doc/Core/术语与坐标系（idx-time-offset）.md`

## 2) K 线消费（finalized）与事件驱动

trade_system 把“finalized 入口”收敛到单点编排器，避免多处散落逻辑：

- `KlineFinalizeOrchestrator.handle_finalized(...)`：
  - 可选 `writeback`：触发 `DataService.auto_sync_if_needed(...)`（本质是把历史 OHLCV 真源落到本地 datadir）。
  - 可选 `ingest`：把 finalized_time 推进到 ledger/artifacts；并把增量（window + patch）放入 live-delta stream 的队列。
  - **去重 + 冷却**：避免高频触发导致 download-data 风暴。
  - **按需 ingest**：默认仅当存在 live-delta 订阅时才 ingest（无人看图时可 no-op）。

代码定位：
- `../trade_system/user_data/backend/app/services/market/kline_finalize_orchestrator.py`

## 3) 因子计算（factor2）与“冷热”语义

trade_system 的“冷热”不是存储介质意义上的 hot/cold，而是 **因子输出语义**：

- `history`：冷数据，append-only，切片阶段必须纯过滤（禁止重算/末态倒推）。
- `head`：热数据，允许短窗重算/重绘，但必须无未来函数（只用 `<=t` 输入）。

坐标系/主键约束：
- 主键：`candle_time`（跨窗口稳定）。
- `idx`：仅窗口内编号；引入 `preload_offset` 时，所有 idx 语义字段必须统一平移。

权威文档入口：
- `../trade_system/user_data/doc/Core/核心类 2.1.md`
- `../trade_system/user_data/doc/Core/术语与坐标系（idx-time-offset）.md`

## 4) 存储：Factor Ledger / SlotDelta Ledger（同源底座）

### 4.1 Factor Ledger（snapshots source）

目标：在任意 `candle_time=t`，可随机访问并重建 `snapshots(t)=history(t)+head(t)`，且支持 append-only 增量写入与 tail-upsert（同 time 多版本取最新 seq）。

权威协议：
- `../trade_system/user_data/doc/Core/Contracts/factor_ledger_v1.md`

### 4.2 SlotDelta Ledger（绘图增量底座）

目标：持久化每根 K 的“指令集合变化”（slot diff + catalog_patch），实现：

- replay window 与 live cursor diff **同源**；
- overlay 全量也从同一份 slot delta 重建（避免“overlay 重算 vs live/replay 漂移”）。

权威协议：
- `../trade_system/user_data/doc/Core/Contracts/slot_delta_ledger_v1.md`

## 5) 绘图（Plot）：插件 → slots → diff → 前端渲染

trade_system 绘图链路的关键是“插件装配 + slot 语义”：

- `FactorEngine`：纯装配入口（不持有增量态），负责参数解析与插件加载、暴露 overlay_features。
  - `../trade_system/user_data/factors/engine.py`
- Plugin 产出 `desired_slots`：`slot_key -> instruction|None`（None 表示清理 slot）。
- 后端以 slot diff 的形式对外提供：
  - `instruction_catalog_patch`：增量补齐指令定义（避免重复发送大定义）。
  - `window`：包含 checkpoints/diffs（客户端可重建 active_ids）。
- 前端将 patch 并入 catalog、根据 window 重建 activeIds，再映射到 instruction 列表渲染。

前端参考（理解“patch + window → instructions”）：
- `../trade_system/user_data/frontend/src/hooks/useLiveDeltaOverlay.ts`

## 6) 给 trade_canvas 的可继承要点（只继承不变量）

建议只继承这些“硬约束/不变量”，不要继承实现复杂度：

1) **closed candle 是权威输入**：forming 蜡烛只展示，不进入因子/信号/落库。
2) **时间主键**：持久化主键统一用 `candle_time`；`idx` 只能作为窗口视图编号。
3) **冷热语义**：history=append-only + 纯切片；head=短窗重算 + 无未来函数。
4) **读写分离**：读路径不重算、不隐式写入；缺失返回 build_required/ledger_missing。
5) **增量一致性**：`seed ≡ incremental`（同输入，结果可复现）。
