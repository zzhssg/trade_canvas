---
title: 第8关：从 IngestSupervisor 到 Binance WS，讲透实时摄取调度
status: done
created: 2026-02-11
updated: 2026-02-11
---

# 第8关：从 IngestSupervisor 到 Binance WS，讲透实时摄取调度

前面你已经学会“写链路正确”和“故障可补偿”。  
这一关我们看实时系统里最容易失控的地方：**订阅调度与资源治理**。

一句话背景：  
WS 客户端会随时订阅/退订，交易所流会抖，机器资源有限。  
如果调度做不好，系统不是“算错”，而是“直接扛不住”。

---

## 0. 先给总纲

实时摄取调度的核心不是“连上 WS 就行”，而是：

**谁该常驻、谁按需拉起、谁该被回收、失败后如何降噪恢复。**

trade_canvas 里这套逻辑主要由两层完成：

1. `IngestSupervisor`：作业生命周期与容量治理。  
2. `run_binance_ws_ingest_loop`：单作业内的数据摄取与刷盘发布。

---

## 1. Supervisor 是“作业调度器”，不是“数据处理器”

`IngestSupervisor` 管的是 job，不是 candle 算法。  
每个 job 记录：

- `series_id`
- `refcount`（被多少客户端引用）
- `source`（当前是 binance_ws）
- `last_zero_at`（归零时间，用于空闲回收）
- `crashes / last_crash_at`（故障观测）

你可以把它理解成“实时作业控制平面”。

---

## 2. 两种作业来源：白名单常驻 vs 按需订阅

### 白名单常驻（pinned）

- `start_whitelist()` 启动白名单作业；
- `refcount = -1` 表示常驻，不参与按需回收。

### 按需订阅（ondemand）

- WS `subscribe` 时触发 `supervisor.subscribe(series_id)`；
- 若不存在 job 则尝试拉起；
- `unsubscribe` 时 refcount--，归零后进入可回收状态。

这就是“稳定流量常驻、突发流量弹性”的混合策略。

---

## 3. 容量治理：满载时不是硬崩，而是优先淘汰空闲作业

`ondemand_max_jobs` > 0 时，supervisor 会执行容量策略：

1. 若容量未满：直接拉起新 job。  
2. 若容量已满：先找 `refcount == 0` 且最早空闲的 job 淘汰。  
3. 若没有可淘汰空闲作业：拒绝新订阅（返回容量不足）。

这就是典型的“最小影响淘汰”：优先踢空闲，不影响活跃连接。

---

## 4. Idle Reaper：把“忘记退订”的泄漏问题变成可控

仅靠 `unsubscribe` 不够稳，客户端断线/异常退出经常会漏清理。  
所以 supervisor 还有 `_reaper_loop`：

- 每秒扫一次 job；
- 对非白名单、`refcount=0` 且超过 `ondemand_idle_ttl_s` 的作业执行 stop+cancel；
- 完成后从 job 表删除。

这相当于“连接泄漏保险丝”。

---

## 5. 一个很聪明的点：派生周期订阅会归一到基础周期作业

当启用 derived timeframe 时，  
订阅 `5m` 这种派生 series，不会单独拉一条 5m WS，而是归一到 base（比如 1m）作业。

意义非常大：

- 避免重复拉流（省连接、省流量）；
- 派生周期由本地 fanout 生成，口径统一；
- 调度层复杂度不随周期数线性爆炸。

这是真正的架构收益，不是语法技巧。

---

## 6. 单作业摄取循环：closed/forming 分流 + 批量刷盘

`run_binance_ws_ingest_loop` 里有几个关键动作：

1. 解析 payload 得到 `(candle, is_final)`。  
2. `forming`：
   - 只走 hub 发布；
   - 有最小间隔节流（`forming_min_interval_ms`）；
   - 不进 factor 主链路。
3. `closed`：
   - 进入缓冲 `buf`；
   - 达到 `batch_max` 或超过 `flush_s` 触发 flush。

flush 时会先做去重与时间单调过滤，再把 batch 交给 pipeline。

---

## 7. 为什么 flush 里先 `pipeline.run(publish=False)`，再手动 publish

这一步很关键：

- 先统一落库和主链路推进（db/factor/overlay）；
- 拿到 `pipeline_result`（含 `rebuilt_series`）；
- 再统一发布 closed batch 和 system rebuild 事件。

好处：

- 发布只在“写链路完成后”发生，减少读到半状态；
- 可拿到准确的 `duration_ms/rebuilt_series` 做日志与监控；
- derived 批次可与 base 批次一起有序发布。

---

## 8. 冷启动兜底：无 head 且指定来源时可先从 freqtrade 引导

在 `history_source == "freqtrade"` 且该 series 尚无 head 时，  
WS loop 会尝试 `maybe_bootstrap_from_freqtrade`。

这避免了“刚启动时完全空窗，前端订阅啥也没有”的糟糕体验。

注意：这是引导兜底，不改变 closed-candle 主链路权威性。

---

## 9. 失败模型：记录 crash，不在循环里盲目自旋

Supervisor 启动的 runner 对作业异常会：

- 记录 `crashes` 与 `last_crash_at`；
- `sleep(2s)` 后结束当前 task。

这比“无限立即重试”更安全，避免异常风暴把 CPU 打满。  
配合 debug snapshot，你可以很快定位哪条 series 在频繁崩。

---

## 10. 从 WS 路由到调度器：控制流闭环

`/ws/market` 的控制流是：

1. `WsMessageParser` 解析 subscribe/unsubscribe；
2. `WsSubscriptionCoordinator` 处理 catchup + emit；
3. 若 `enable_ondemand_ingest` 开启，则调用 supervisor 的 subscribe/unsubscribe；
4. 断连时 `cleanup_disconnect` 统一清理本连接关联订阅。

这条闭环保证了“协议层动作”能映射到“调度层状态”。

---

## 11. 这关的工程方法论（可迁移）

- **Control plane / data plane 分离**：调度器管作业，loop 管数据。  
- **Capacity with graceful degradation**：满载时先淘汰空闲，实在不行明确拒绝。  
- **One source, many derived**：派生口径由本地 fanout，不重复拉外部源。  
- **Publish after persist**：先写后发，降低前端时序错乱概率。

---

## 12. 代码锚点（建议顺读）

- `backend/app/ingest_supervisor.py`
- `backend/app/ingest_binance_ws.py`
- `backend/app/market_ws_routes.py`
- `backend/app/market_data/ws_services.py`
- `backend/app/market_runtime_builder.py`
- `backend/tests/test_ingest_supervisor_capacity.py`
- `backend/tests/test_ingest_supervisor_whitelist_fallback.py`
- `backend/tests/test_market_ws.py`

---

## 13. 过关自测

1. 为什么白名单 job 用 `refcount=-1`？  
2. `ondemand_max_jobs` 满了时，系统如何决定淘汰谁？  
3. 为什么 derived 订阅要归一到 base series job？  
4. forming 为什么要节流且不进 factor 主链路？  
5. 为什么要“先 pipeline 落库，再手动 publish”？

能把这 5 题讲清楚，你就掌握了实时摄取调度的核心思维。
