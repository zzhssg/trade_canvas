---
title: 第2关：用 pen 因子链讲透插件架构与增量算法
status: done
created: 2026-02-11
updated: 2026-02-11
---

# 第2关：用 pen 因子链讲透插件架构与增量算法

这一关的目标是：  
把“插件架构 + 增量算法 + 写读一致性”一次打通，而不是只看懂某个函数。

---

## 0. 一图流：先看整条链

```text
CandleClosed
  -> IngestPipeline.run_sync
  -> FactorOrchestrator.ingest_closed
     -> RebuildLoader.bootstrap_state
     -> FactorTickExecutor.run_incremental (topo)
        pivot -> pen -> zhongshu -> anchor
     -> FactorStore.insert_events + insert_head_snapshot
  -> /api/factor/slices
     -> FactorReadService (freshness)
     -> FactorSlicesService (topo build)
     -> PenSlicePlugin(history + head)
```

`pen` 在链路中的位置：上接 `pivot`，下游供给 `zhongshu` / `anchor`，并被前端和 freqtrade 同步消费。

---

## 1. 为什么 `pen` 是学插件架构的最佳切口

`pen` 不是孤立算法，它天然处在系统中间层：

- 依赖声明：`depends_on=("pivot",)`。
- 写侧有事件：`pen.confirmed`。
- 读侧有头部：`pen.extending` / `pen.candidate`。
- 下游有消费者：`zhongshu`、`anchor`、overlay、freqtrade。

所以你学 `pen`，就是在学“插件如何在拓扑图中协作”。

---

## 2. 插件架构三层硬约束（不是约定俗成）

### 2.1 插件契约层

每个插件都要声明 `spec.factor_name` 与 `depends_on`，并实现 `run_tick`。  
缺 `run_tick` 直接失败，防止“静默降级”。

### 2.2 DAG 调度层

`FactorGraph` 会校验：

- 重名（duplicate）
- 缺依赖（missing_deps）
- 依赖环（cycle）

然后产出稳定拓扑序（同层按名字排序），保证调度确定性。

### 2.3 Manifest 一致性层

写侧 processor 和读侧 slice plugin 必须：

- 因子集合一致
- `depends_on` 一致

否则 `build_factor_manifest` 直接报错。  
这一步非常关键：把“写出来的账本”和“读出来的快照”绑定成同一契约。

---

## 3. `pen` 的增量算法：核心其实只有五步

算法核心在 `append_pivot_and_confirm`，维护 `effective_pivots`：

1. `effective` 为空：直接 append。
2. 新 pivot 与最后一个同方向：只保留更极值的那个（同向替换）。
3. 反方向：append 到 `effective`。
4. 长度 `< 3`：还不能确认笔。
5. 长度 `>= 3`：`effective[-3] -> effective[-2]` 确认成笔，`visible_time = effective[-1].visible_time`。

口令版：**同向替换，反向追加，三点成笔，后一确认。**

这套设计的价值：

- 没有未来函数（不偷看未来 candle）。
- 延迟确认可解释（确认需要反向 pivot 盖章）。
- 自然支持增量推进（每 tick 只处理新增候选）。

---

## 4. 幂等与可重放：`event_key` 才是工程生命线

`pen.confirmed` 事件 key：

`confirmed:{start_time}:{end_time}:{direction}`

写库时有唯一约束 `(series_id, factor_name, event_key)`，冲突 `DO NOTHING`。  
这意味着：

- 重试不会重复写脏数据。
- 增量补算不会造成事件膨胀。
- 回放可重入，结果稳定。

这就是“增量系统能长期跑”的关键，不是算法本身有多花哨。

---

## 5. bootstrap：增量前先恢复状态，不是从零猜

`FactorRebuildStateLoader` 会先把历史事件按插件归桶，再按 topo 调用各插件 `bootstrap_from_history`。

对 `pen` 而言：

- 从 `rebuild_events["pen"]` 里取历史 `pen.confirmed`。
- 做 payload 规范化（字段类型稳定）。
- 恢复 `confirmed_pens`，供后续 tick 增量续跑。

这让系统做到“可补窗、可重启、可恢复”，不需要每次全量重算。

---

## 6. 读侧 `PenSlicePlugin`：历史与头部分层拼装

`PenSlicePlugin.build_snapshot` 做两件事：

1. `history.confirmed`：来自 `pen_confirmed` bucket（冷历史）。
2. `head`：
   - 优先读 `head_rows["pen"]`（已有快照）。
   - 没有就 fallback：拉 candles + `build_pen_head_snapshot` 重建 `extending/candidate`。

这就是典型的“history/head 分层”：

- history 追求可追溯、稳定；
- head 追求当前可用、可恢复。

---

## 7. `pen` 如何驱动下游协作

### 7.1 驱动 zhongshu

`zhongshu` 在 tick 中消费 `new_confirmed_pen_payloads`，更新中枢状态并发出 `zhongshu.dead` 事件。

### 7.2 驱动 anchor

`anchor` 会结合 confirmed/candidate pen 强度做换锚决策，发 `anchor.switch`。

### 7.3 驱动策略（freqtrade）

freqtrade 适配层把 `pen.confirmed` 映射为：

- `tc_pen_confirmed`
- `tc_pen_dir`
- `tc_enter_long` / `tc_enter_short`

同一笔事件，可被图表和策略同时消费，口径一致。

---

## 8. 这条链背后的工程方法论

- 声明依赖，不写隐式顺序。
- 增量推进，不做无谓全量。
- 事件幂等，先保证可重入再谈性能。
- 写读分离，但契约必须同源一致。
- fail-fast 优于 silent fallback。

---

## 9. 代码锚点（建议边看边对拍）

- `backend/app/factor_processor_pen.py`
- `backend/app/factor_tick_executor.py`
- `backend/app/factor_graph.py`
- `backend/app/factor_manifest.py`
- `backend/app/factor_rebuild_loader.py`
- `backend/app/factor_slices_service.py`
- `backend/app/factor_slice_plugins.py`
- `backend/app/factor_head_builder.py`
- `backend/app/factor_store.py`
- `backend/app/freqtrade_adapter_v1.py`

---

## 10. 过关自测（你应当能回答）

1. 为什么 pen 确认至少需要 3 个有效 pivot？
2. 为什么同方向 pivot 要替换成更极值，而不是追加？
3. 为什么 `event_key` 不带 `visible_time` 也能保持幂等？
4. 为什么 manifest 要强制写侧/读侧 `depends_on` 一致？
5. 当 pen head 快照缺失时，读侧如何自愈构建？

如果这五题你能讲清楚，第 2 关就过了。
