---
title: 第9关：从 WS 协议到 catchup 机制，讲透客户端时序一致性
status: done
created: 2026-02-11
updated: 2026-02-11
---

# 第9关：从 WS 协议到 catchup 机制，讲透客户端时序一致性

这关要解决一个前后端联调里最常见、也最隐蔽的问题：

**同一个客户端连接，既要补历史（catchup），又要收实时（live），如何不重不漏、不乱序？**

如果这件事处理不好，前端就会出现：

- 同一根 K 线重复出现；
- gap 提示错位；
- 历史和实时拼接时序混乱。

trade_canvas 的 WS 链路就是为了解这件事。

---

## 0. 先给一句总纲

客户端时序一致性的核心是：

**每个连接维护一份 `last_sent_time`，所有 catchup/live 发送都以“只发大于 last_sent 的 candle”作为硬门槛。**

再配合 gap 检测与可选回补，才能做到“可追平 + 可持续”。

---

## 1. 协议层先收口：消息类型与错误类型固定

WS 协议消息类型是明确枚举的：

- 入站：`subscribe` / `unsubscribe`
- 出站：`candle_closed` / `candles_batch` / `candle_forming` / `gap` / `system` / `error`

错误也有固定 code（如 `bad_request` / `capacity`）。  
这意味着前端可以做确定性状态机，不用猜字符串。

---

## 2. 订阅握手不是直接开始推流，而是“解析 -> catchup -> emit”

`/ws/market` 里处理 subscribe 的流程是：

1. `WsMessageParser` 校验 envelope/type/series_id/since/supports_batch。  
2. `WsSubscriptionCoordinator.handle_subscribe` 执行：
   - `derived_initial_backfill`（必要时先补基础数据）
   - hub subscribe（记录 sub 信息）
   - 读取 catchup candles
   - 结合 `last_sent` 做去重窗口
   - gap 治疗（heal）
   - 构造 emit payload（batch 或 stream）
3. 发送 payload，并写回 `last_sent_time`。

这不是“收到 subscribe 就从 now 开推”，而是一次带时序治理的握手。

---

## 3. catchup 的关键公式：`effective_since = max(since, last_sent)`

为什么要这样算？  
因为同一连接可能重复订阅、或者先收过一部分实时。

若只用用户传的 `since`，就会把已经发过的 candle 再发一遍。  
所以系统用：

- `effective_since = since`
- 若 `last_sent > since`，则提升为 `last_sent`
- catchup 仅保留 `candle_time > effective_since`

这一步就是“防重复发送”的核心护栏。

---

## 4. gap 语义：不是报错，而是时序告警协议

gap 的定义：

- 订阅方期望下一根时间是 `expected_next_time`；
- 实际收到第一根是 `actual_time`；
- 若 `actual_time > expected_next_time`，发送 `gap` 消息。

gap 不等于失败。它是告诉前端：“中间有洞，你要知道这不是连续序列。”

---

## 5. gap 还能“先治后发”：可选回补机制

`CandleHub` 支持 `gap_backfill_handler`：

1. 发现 gap 后，先尝试回补 `expected_next_time ~ actual_time` 之间缺失 candle；
2. 若补回来，就先发补回数据，再发 live；
3. 若补不回来，再显式发 `gap` 通知。

这就是“尽量自愈，无法自愈时显式告警”的策略。

---

## 6. batch 与 stream 双模式：同语义，不同传输形态

订阅时 `supports_batch=true`：

- catchup 优先走 `candles_batch`，减少帧数；
- live 仍可能是 `candle_closed`（按发布路径）。

`supports_batch=false`：

- 逐根 `candle_closed` 输出；
- 同样遵守 gap 与 last_sent 规则。

重点是：语义一致，只有网络形态不同。

---

## 7. 竞态场景怎么防：catchup 与 live 同时到来不重复

经典竞态：

- 客户端刚 subscribe，catchup 还在读；
- 同时新 live candle 已 ingest 并尝试推送。

系统防线是双重的：

1. catchup 阶段基于 `effective_since` 过滤；
2. Hub 发送前再用 `last_sent_time` 做 `_should_skip_candle` 检查。

结果是：同一 candle 不会因为竞态被重复发两次（测试里有专门 race case 覆盖）。

---

## 8. 容量拒绝也必须协议化：明确 `capacity` 错误，不偷发数据

当 ondemand ingest 达到容量上限，第二个订阅会被拒绝：

- 返回 `{"type":"error","code":"capacity","message":"ondemand_ingest_capacity","series_id":...}`
- 且不会偷偷发该 series 的 catchup/live 数据。

这一步很重要：  
拒绝必须是“显式拒绝 + 数据隔离”，不能一边报错一边夹杂数据。

---

## 9. forming 在 WS 里的角色：实时体验增强，不参与闭合序列

WS 还会推 `candle_forming`，但它有两个边界：

- 仅在 `candle_time > last_sent_time` 时推；
- 由最小间隔做节流（防刷屏）。

所以 forming 不会破坏 closed 序列的一致性，只是前端体验增强层。

---

## 10. 这套机制背后的工程原则

- **Single monotonic cursor per connection**：每连接一份 last_sent 游标。  
- **Catchup/live same gate**：历史和实时都过同一“去重门”。  
- **Gap is first-class message**：缺口是协议对象，不是日志噪声。  
- **Degrade explicitly**：容量不足要明确拒绝，不给半状态。

---

## 11. 代码锚点（按链路读）

- `backend/app/ws_protocol.py`
- `backend/app/market_ws_routes.py`
- `backend/app/market_data/ws_services.py`
- `backend/app/market_data/orchestrator.py`
- `backend/app/ws_hub.py`
- `backend/tests/test_market_ws.py`
- `backend/tests/test_ws_hub_delivery.py`
- `backend/tests/test_market_data_services.py`
- `backend/tests/test_e2e_user_story_market_sync.py`

---

## 12. 过关自测

1. 为什么 `effective_since` 要取 `max(since, last_sent)`？  
2. gap 消息在协议里承担什么角色，为什么不能只打日志？  
3. `supports_batch` 改变了什么，没改变什么？  
4. catchup/live 竞态时，系统靠哪两层机制避免重复发送？  
5. 容量拒绝时为什么必须保证“被拒系列不出任何数据帧”？

如果这 5 题能讲顺，你就掌握了 WS 时序一致性的核心。
