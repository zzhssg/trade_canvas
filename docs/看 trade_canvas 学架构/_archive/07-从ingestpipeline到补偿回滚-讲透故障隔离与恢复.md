---
title: 第7关：从 IngestPipeline 到补偿回滚，讲透故障隔离与恢复
status: done
created: 2026-02-11
updated: 2026-02-11
---

# 第7关：从 IngestPipeline 到补偿回滚，讲透故障隔离与恢复

前面几关你学了“怎么正确算”。  
这一关我们讲“算崩了怎么办”。

真正上线系统的分水岭，不是没有错误，而是：

- 错误发生时能不能定位到具体步骤；
- 半成功状态能不能补偿回滚；
- 错误之后有没有可控恢复路径，而不是手工救火。

trade_canvas 的 `IngestPipeline` 就是这套故障治理的主战场。

---

## 0. 先记一句总纲

`IngestPipeline` 的设计思想是：

**把一次写链路拆成可观测步骤，失败时返回结构化错误，并按开关执行最小补偿。**

这句话里有三个关键词：步骤化、结构化、可开关补偿。

---

## 1. 一次 ingest 不是一个黑盒事务，而是分段推进

`_run_sync` 内部按 series 顺序做三段主步骤：

1. `store.upsert_many_closed`
2. `factor.ingest_closed`
3. `overlay.ingest_closed`

每段成功都会记录 `IngestStepResult(name, duration_ms)`。  
也就是说，失败时你不只知道“失败了”，还知道“失败在第几段”。

这就是“步骤化可观测”的第一层价值。

---

## 2. 为什么要单独定义 `IngestPipelineError`

普通 `RuntimeError` 只会告诉你一串字符串；  
`IngestPipelineError` 会带结构化上下文：

- `step`：失败步骤（store/factor/overlay）
- `series_id`：失败序列
- `cause`：原始异常
- `compensated`：是否执行了补偿
- `overlay_compensated`：是否成功 reset overlay
- `candle_compensated_rows`：是否回滚了新写入 candle 行数
- `compensation_error`：补偿过程本身的异常

这让上层（`MarketIngestService`）能把错误做成“可读、可监控、可检索”的调试事件。

---

## 3. 关键设计：只回滚“本次新增 candle”，不动历史数据

很多系统补偿会粗暴 delete 一大片，风险很高。  
这里的设计更保守：

1. 先在 upsert 前查 `existing_times`；
2. 计算本次 `new_candle_times`；
3. 失败后只删除这些新增时间点。

这就是最小破坏原则：  
**补偿只撤销本次副作用，不回滚历史真源。**

---

## 4. 两类补偿开关：overlay reset 与 candle rollback

补偿不是硬编码必开，而是 runtime flags 控制：

- `TRADE_CANVAS_ENABLE_INGEST_COMPENSATE_OVERLAY_ERROR`
  - overlay 失败后尝试 `overlay.reset_series`
- `TRADE_CANVAS_ENABLE_INGEST_COMPENSATE_NEW_CANDLES`
  - factor/overlay 失败后回滚本次新 candle

这让你可以在不同阶段选择策略：

- 研发环境更激进（补偿全开）；
- 线上环境按风险和观测能力渐进放开。

---

## 5. 一个容易忽略的细节：`rebuilt_series` 会先触发 overlay reset

当 factor 侧返回 `rebuilt=True`（通常 fingerprint 触发重建）时，  
pipeline 会把 series 放进 `rebuilt_series`，然后在 overlay 阶段先 `reset_series` 再重算。

这步是防“旧 overlay 残影”的关键。  
否则你可能出现：factor 已是新口径，overlay 还混着旧版本定义。

---

## 6. 错误到 API 的映射：可观测信息不丢失

`MarketIngestService.ingest_candle_closed` 捕获 `IngestPipelineError` 后会做两件事：

1. 往 debug hub 发 `write.http.ingest_candle_closed_error`，带完整补偿字段；
2. 抛 `ServiceError(500)`，detail 规范化为 `ingest_pipeline_failed:<step>:<series_id>`。

这让你同时拥有：

- 面向客户端的稳定错误形态；
- 面向运维的高信息调试数据。

---

## 7. 自动补偿不够时，系统还提供“显式修复路径”

当 draw 侧被判定 `ledger_out_of_sync:overlay`，  
可以通过受控接口 `/api/dev/repair/overlay` 执行 repair（受 `TRADE_CANVAS_ENABLE_READ_REPAIR_API` 开关保护）：

1. 先 `refresh_series_sync` 推进写链路；
2. 再 `overlay.reset_series`；
3. 最后 `overlay.ingest_closed` 重建；
4. 校验 factor/overlay head 是否达到 aligned_time。

这条路径把“手工救火”变成“可脚本化修复”。

---

## 8. 这套故障治理背后的工程原则

- **Fail with context**：失败必须携带步骤与补偿信息。
- **Compensate minimally**：只撤销本次副作用，不误删历史。
- **Feature-flagged recovery**：补偿策略必须可开关、可回滚。
- **Repair as API**：恢复流程产品化，不靠人肉 SQL。

这几条原则你可以迁移到任何事件驱动写链路。

---

## 9. 代码锚点（按故障路径阅读）

- `backend/app/pipelines/ingest_pipeline.py`
- `backend/app/market_ingest_service.py`
- `backend/app/read_models/repair_service.py`
- `backend/app/repair_routes.py`
- `backend/app/runtime_flags.py`
- `backend/tests/test_ingest_pipeline.py`
- `backend/tests/test_market_ingest_error_observability.py`
- `backend/tests/test_read_repair_api.py`

---

## 10. 过关自测

1. 为什么 `IngestPipelineError` 要有 `step` 和补偿字段？  
2. 为什么补偿只删 `new_candle_times`，而不是按时间范围全删？  
3. `overlay_compensate_on_error` 和 `candle_compensate_on_error` 的边界是什么？  
4. `rebuilt_series` 为什么会强制 overlay reset？  
5. 在什么情况下应触发 `/api/dev/repair/overlay` 而不是重启服务？

如果你能把这 5 题讲清楚，这关就过了。
