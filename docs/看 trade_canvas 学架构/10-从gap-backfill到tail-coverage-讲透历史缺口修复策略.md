---
title: 第10关：从 gap backfill 到 tail coverage，讲透历史缺口修复策略
status: done
created: 2026-02-11
updated: 2026-02-11
---

# 第10关：从 gap backfill 到 tail coverage，讲透历史缺口修复策略

你现在已经知道：

- 实时链路会持续推新 K；
- 前端会不断订阅、重连、补历史；
- 数据源（freqtrade / 交易所）并不保证永远连续。

所以系统必须面对一个现实：**“洞”一定会出现**。  
区别只在于你是“被洞打崩”，还是“把洞当一等公民治理”。

trade_canvas 这一关的核心能力，就是后者。

---

## 0. 先给一句总纲

历史缺口治理不是一个开关，而是三层协同：

1. **WS 层补洞**：处理“连接级时序洞”（gap backfill）。
2. **读路径补尾**：处理“序列级覆盖不足”（tail coverage）。
3. **启动期追平**：处理“服务冷启动落后”（startup sync）。

三层共同目标：

**尽量补齐；补不齐就明确暴露；永远不偷偷篡改时序语义。**

---

## 1. 先区分两种“洞”：不是一个问题

### 第一种：连接时序洞（Gap）

白话：客户端刚连上，理论下一根该是 160，结果先看到 220。中间少了一段。

系统定义：

- `expected_next_time = last_sent_time + timeframe_s`
- 如果 `actual_time > expected_next_time`，这是 gap。

### 第二种：尾部覆盖洞（Tail Coverage 不足）

白话：你读最近 N 根，仓库里其实没有那么多，尾巴空了。

系统定义：

- 对目标窗口 `[start_time, end_time]` 统计已覆盖根数；
- 若 `< target_candles`，说明覆盖不足，需要回补。

这两类洞一个发生在“**连接发送语义**”，一个发生在“**存储覆盖语义**”。

---

## 2. WS 补洞：先尝试补，再决定要不要发 gap

主战场在 `CandleHub`。

关键流程（`_prepare_sendable_with_gap`）：

1. 先过滤重复（`_should_skip_candle`，只发 `> last_sent_time`）。
2. 计算 `expected_next_time`。
3. 若第一根 `first_time > expected_next_time`，触发 `_recover_gap_candles`。
4. 把 recovered 与原 sendable 做去重+排序（`_merge_candles`）。
5. 仍然有洞才发 `gap` payload。

这意味着：

- **有能力自愈时**：优先发补回后的 closed 序列；
- **无能力自愈时**：明确发 `gap`，告诉前端“这里确实有断层”。

这就是“先治后报”的工程策略。

---

## 3. gap backfill handler：把“补洞动作”从 Hub 解耦出去

`build_gap_backfill_handler` 做了一个很关键的设计：

- Hub 不直接碰 backfill 细节；
- handler 里用 `BackfillService.backfill_gap` 先补；
- 再用 `reader.read_between(expected_next, actual-tf)` 取可发送数据。

并且这个能力受 `enabled` 开关硬控（`TRADE_CANVAS_ENABLE_MARKET_GAP_BACKFILL`）。

这就是标准插件化思路：

- **Hub 定义协议与时序门槛**；
- **BackfillService 实现“如何补”**；
- **flag 决定“是否启用”**。

所以你可以演进 backfill 实现，而不破坏 WS 主协议。

---

## 4. 读路径补尾：每次 HTTP 读取前先“补齐最近窗口”

`/api/market/candles` 在读数据前会判断：

- `enable_market_auto_tail_backfill` 是否打开；
- 目标根数 `target = min(limit, max_candles)`（若配置了上限）；
- 调 `runtime.backfill.ensure_tail_coverage(series_id, target, to_time=None)`。

注意这个设计很实用：

- 用户来读数据时，系统顺手做“最近窗口修补”；
- 不需要等全局任务慢慢追；
- 但通过 `max_candles` 防止一次请求拉爆回补量。

这就是把“读请求”变成“温和修复触发器”。

---

## 5. `ensure_tail_coverage` 的四级补洞决策树（重点）

这是本关最值钱的算法骨架。

### 第一级：主来源回补（tail_backfill_fn）

默认走 `backfill_tail_from_freqtrade`。失败不抛死，记录 error，继续 best-effort。

### 第二级：本地可聚合回补（derived <- 1m）

若目标周期是派生周期（比如 5m）：

- 会尝试从本地 `1m` closed 滚成目标周期；
- 只在满足条件时启用：目标周期是 1m 的整数倍，且不超过 900 秒（15m）。

这层非常“省外部依赖”：能本地算就不出网。

### 第三级：CCXT 区间回补（可选）

只有同时满足才会触发：

- 覆盖仍不足；
- `enable_ccxt_backfill=True`；
- 且 `allow_ccxt=True`。

`allow_ccxt` 的定义很关键：

- `to_time is not None`（显式目标时间）**或**
- `enable_ccxt_backfill_on_read=True`。

也就是说：默认读路径不是无脑打外部源。

### 第四级：状态收敛与结果语义

- 重新统计覆盖；
- 更新 `MarketBackfillProgressTracker`：`begin -> succeed/fail`；
- `note` 用 `tail_coverage_done / partial / best_effort_failed` 标识收敛状态。

返回值语义也做了区分：

- `to_time=None`：返回 `max(filled, covered)`（读路径偏“可用性”）；
- `to_time!=None`：返回 `covered`（目标时间窗口偏“准确覆盖”）。

---

## 6. 启动期追平：把“冷启动落后”前置消化

`run_startup_kline_sync` 在服务启动后按白名单 series 执行：

1. 计算每个 series 的 `target_time`（期望最新 closed）。
2. `ensure_tail_coverage(..., to_time=target_time)` 做追平。
3. 可选触发 `ingest_pipeline.refresh_series_sync`，让因子/叠加读模型一起跟上。
4. 输出 `synced / lagging / errors` 统计与逐 series 结果。

这层的意义是：

- 在第一批用户请求到来前，先把明显滞后消化掉；
- 把“首屏空洞”从线上交互问题，前移为启动治理问题。

---

## 7. 可观测性：补洞不是黑箱，要能量化“补了多少，还差多少”

`MarketBackfillProgressTracker` 记录：

- 起始缺口秒数/根数；
- 当前缺口秒数/根数；
- `progress_pct`；
- state（running/succeeded/failed）与 note/error。

`/api/market/health` 会把这些拼成健康结论：

- `green`：已追平；
- `yellow`：正在补或刚补过但仍有缺口；
- `red`：明显滞后且近期无有效补洞。

这一步非常架构化：

**“补洞策略”必须配“健康视图”，否则就是玄学调参。**

---

## 8. 这套设计背后的通用工程方法论

- **分层治理同一问题**：连接层洞、存储层洞、启动层洞分别处理。  
- **Best-effort + 显式告警并存**：先补，补不齐就协议化暴露。  
- **本地优先，外部兜底**：先 freqtrade/本地 rollup，再 CCXT。  
- **开关化放量**：所有高风险补洞能力都能 kill-switch。  
- **结果可量化**：每次补洞都有“进度、状态、原因”。

如果你以后做日志补偿、缓存回暖、消息重放，也能直接套这五条。

---

## 9. 代码锚点（建议按这条链路读）

- `backend/app/market_http_routes.py`
- `backend/app/market_data/read_services.py`
- `backend/app/market_data/orchestrator.py`
- `backend/app/ws_hub.py`
- `backend/app/market_backfill.py`
- `backend/app/startup_kline_sync.py`
- `backend/app/market_health_service.py`
- `backend/tests/test_market_data_services.py`
- `backend/tests/test_ws_hub_delivery.py`
- `backend/tests/test_market_ws.py`
- `backend/tests/test_startup_kline_sync.py`
- `backend/tests/test_market_health_routes.py`

---

## 10. 过关自测（能讲顺就真的会了）

1. 为什么 gap 和 tail coverage 必须分两条治理链，而不能一个函数全包？  
2. `ensure_tail_coverage` 为什么要“主来源 -> 本地 rollup -> CCXT”三段式？  
3. 为什么 `to_time=None` 时默认不一定触发 CCXT？这背后的成本控制逻辑是什么？  
4. 为什么 WS 层在补洞失败时要发 `gap`，而不是静默跳过？  
5. 启动期追平和读路径自动补尾分别在什么时候更有价值？

如果你能把这 5 题用自己的话讲清楚，你已经从“会写接口”进阶到“会设计修复系统”了。
