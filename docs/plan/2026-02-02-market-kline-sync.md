---
title: 市场 K 线同步（Whitelist 实时 + 非白名单按需补齐）
status: 开发中
owner:
created: 2026-02-02
updated: 2026-02-02
---

## 背景

trade_canvas 需要把“市场 K 线（`CandleClosed`）”作为全链路真源：同时驱动因子引擎（策略）与图表展示，并支持：

- 白名单币种：持续实时 ingest（闭合后尽快可用）
- 非白名单币种：用户查看时再补齐历史并临时跟随实时（节省资源）

契约与协议真源见：`docs/core/market-kline-sync.md`。

## 目标 / 非目标

### 目标（Do）

- 统一 `series_id / candle_id / candle_time` 坐标系与去重逻辑
- 提供 HTTP 增量读取与 WS 实时订阅（最小 v1）
- 落地 Whitelist 常驻 ingest + 非白名单按需 ingest（带 idle 回收）

### 非目标（Don’t / MVP 不做）

- forming K 的高频推送与复杂 UI（forming 仅显示，不进入因子引擎）
- 历史修订/epoch 强失效的完整机制（可作为后续迭代）
- 多交易所/多市场的全部覆盖（先做 1 个 exchange + 1 个 market type）

## 方案概述

实现三个可替换组件：

1) `CandleStore`：闭合 K 的落库与增量读取（append-only + 幂等 upsert）
2) `CandleIngestor`：上游数据接入（Whitelist 常驻；非白名单订阅期按需）
3) `CandleSyncAPI`：对前端/下游输出（HTTP 分页 + WS 推送）

## 里程碑

- M0（文档/契约）：补齐 SoT 与协议（本 plan + core doc）
- M1（store）：完成最小落库与 HTTP 增量读取
- M2（ws）：完成 WS subscribe + candle_closed 推送 + gap 处理
- M3（whitelist）：完成常驻 ingest（启动补洞 + 实时跟随）
- M4（on-demand）：完成非白名单订阅期开启 ingest + idle 回收
- M5（frontend）：前端接入“HTTP 补齐 → WS 跟随”的同步流程

## 任务拆解

- [x] M1：实现 `CandleStore`（按 `series_id + candle_time` 索引；读路径按 time 升序分页）
- [x] M1：实现 `GET /api/market/candles`（返回 `server_head_time` + `candles[]`）
- [x] M2：实现 WS：`subscribe/unsubscribe` + `candle_closed` 推送
- [x] M2：实现 gap 策略（服务端发 `gap`；前端触发 HTTP 补齐）
- [x] M3：Whitelist 配置入口（文件/环境变量/数据库三选一，确定真源位置）
- [x] M3：Whitelist ingest（启动补洞 + 实时写入 + 广播）
- [x] M4：非白名单按需 ingest（订阅数=0 后 `idle_ttl` 回收）
- [x] M5：前端同步链路（HTTP 循环补齐到 `server_head_time`，再 WS 跟随）
- [x] M5：最小 E2E 验收脚本/测试（store 落库 → HTTP tail=2000 → WS 推送新 candle）

## 风险与回滚

### 风险

- 交易所 WS/REST 延迟或丢包导致 gap（需要明确补齐策略与幂等）
- 非白名单被频繁切换造成资源抖动（需要 ingest worker 限流与 idle 回收）
- 多处定义 `candle_id`/timeframe 对齐规则导致漂移（需要 SoT 单点）

### 回滚

- 关闭非白名单按需 ingest（仅保留 HTTP 历史读取）
- 关闭 WS（前端改为轮询 `server_head_time`，牺牲实时性）
- 保留 store 与幂等写入逻辑，逐步替换 ingest 上游实现

## 验收标准

- 白名单 `series_id`：WS 推送的 `candle_time` 单调递增（客户端去重后不回退）
- 非白名单 `series_id`：首次打开页面完成“HTTP 补齐到 head → WS 跟随”
- gap 场景：服务端发 `gap` 后客户端能自动走 HTTP 补齐并恢复订阅

## 变更记录

- 2026-02-02: 创建（草稿）
- 2026-02-02: 状态变更为开发中；完成 M1/M2 的最小后端闭环
- 2026-02-02: 完成 Whitelist 文件真源与最小 ingest（ccxt 轮询 + WS 广播）
- 2026-02-02: 完成非白名单按需 ingest（WS subscribe 启动；idle_ttl 回收）
- 2026-02-02: 前端接入市场同步（HTTP 增量补齐 + WS 跟随）
- 2026-02-02: 增加最小 E2E 测试覆盖（HTTP tail=2000 + WS 新 candle + 落库）
