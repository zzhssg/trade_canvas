---
title: 第4关：把可复现讲透（幂等、bootstrap、fingerprint 三件套）
status: done
created: 2026-02-11
updated: 2026-02-11
---

# 第4关：把可复现讲透（幂等、bootstrap、fingerprint 三件套）

这关讲一个“看不见但最值钱”的能力：**可复现**。

很多系统表面上能跑，实质上不可靠：

- 同一批数据重放两次，结果不一样；
- 服务重启后，状态和重启前不一致；
- 逻辑升级后，历史账本还是旧口径，读出来半新半旧。

trade_canvas 里，可复现不是口号，而是三层机制叠在一起：

1. 写入幂等（不重复写脏事件）  
2. bootstrap 重建（随时可从历史恢复状态）  
3. fingerprint 回补（口径变化时自动重建账本）

---

## 0. 先记一个总公式

可复现可以记成这句：

`同一输入 + 同一逻辑版本 + 同一调度顺序 = 同一 ledger / 同一 slice`

你会发现，这个式子每一项都在代码里有对应守卫。

---

## 1. 第一层：写入幂等（防“重复执行污染账本”）

### 冲突

网络抖动、重试、补算都会让同一事件被“再执行一次”。  
如果每次都落一行新数据，账本就会越跑越歪。

### 机制

`factor_events` 有唯一约束：

- `UNIQUE (series_id, factor_name, event_key)`

写入使用：

- `ON CONFLICT(series_id, factor_name, event_key) DO NOTHING`

也就是说，同一业务事件重复写，会被数据库吞掉，不污染历史。

### 关键前提

必须保证 `event_key` 稳定且可判等。  
例如 `pen.confirmed` 的 key 只用结构标识（start/end/direction），不带会漂移的临时字段。

---

## 2. 第二层：bootstrap 重建（防“重启后状态失忆”）

### 冲突

内存态（effective pivots、confirmed pens、anchor current 等）重启就丢。  
如果重启后从“空状态”接着跑，结果会偏。

### 机制

`FactorRebuildStateLoader` 在增量前会做三步：

1. 扫描历史事件窗口；
2. 按插件规则“归桶 + 排序”；
3. 按拓扑顺序调用各插件 `bootstrap_from_history` 恢复状态。

这让每次运行都能先回到“上次 head_time 对应的系统状态”，再继续增量。

### 为什么可靠

- 事件是 append-only，可回放；
- 桶排序规则固定；
- 插件 bootstrap 顺序固定（topo）。

所以不是“猜上次内存态”，而是“从历史算回内存态”。

---

## 3. 第三层：fingerprint 回补（防“逻辑升级后旧账本继续被当新账本读”）

### 冲突

你改了因子逻辑、插件依赖、窗口参数，历史 ledger 还是按旧口径算的。  
如果不清理重建，读出来就是“新代码 + 旧账本”的混合体。

### 机制

`build_series_fingerprint` 会把影响口径的关键信息做哈希，包括：

- 拓扑图（graph topo）
- 关键 settings（window/lookback/limit）
- 关键源码文件内容 hash（orchestrator、plugin、pen、zhongshu 等）
- 逻辑版本覆盖字段 `logic_version_override`

每次 ingest 前，`FactorFingerprintRebuildCoordinator.ensure_series_ready` 会对比：

- 一致：正常增量；
- 不一致：触发自动回补流程。

回补流程（默认行为）：

1. candle 侧仅保留最近 N 根（`keep_candles`）；
2. 清空该 series 的 factor events / head / state；
3. 写入新 fingerprint；
4. 后续从保留窗口重新增量构建。

这是“有损重建（保最近窗口）”换“口径一致”的工程折中。

---

## 4. 第四道护栏：读侧 freshness（防“读到过期 ledger”）

即使写侧机制完整，读侧还可能读到“candle 已到但 factor 还没追平”的瞬间。

`read_factor_slices_with_freshness` 给两种策略：

- 非 strict：读前尝试自动 `ingest_closed` 追平；
- strict：不做隐式补算，发现 `factor_head < aligned_time` 直接 409（`ledger_out_of_sync:factor`）。

这一步把“可复现”延伸到“可观测一致性”：宁可报错，不给错数据。

---

## 5. 为什么三件套缺一不可

只做幂等，不做 bootstrap：重启后状态会偏。  
只做 bootstrap，不做 fingerprint：升级后口径会混。  
只做 fingerprint，不做读侧 freshness：用户仍可能读到瞬时脏窗口。

三件套是层层兜底关系，不是可选项清单。

---

## 6. 给工程师的“事故排查顺序”（实战口令）

当你怀疑“结果不复现”时，按这个顺序查：

1. **先查幂等**：同 event_key 是否重复写入？  
2. **再查 bootstrap**：重启后是否按 topo 正确恢复状态？  
3. **再查 fingerprint**：逻辑或参数改了是否触发回补？  
4. **最后查读侧**：strict/freshness 策略是否按预期执行？

这会比盲目打印日志快很多。

---

## 7. 代码锚点（建议按顺序读）

- `backend/app/factor_store.py`
- `backend/app/factor_rebuild_loader.py`
- `backend/app/factor_fingerprint.py`
- `backend/app/factor_fingerprint_rebuild.py`
- `backend/app/factor_orchestrator.py`
- `backend/app/factor_read_freshness.py`
- `backend/tests/test_factor_fingerprint_rebuild.py`
- `backend/tests/test_factor_read_freshness.py`

---

## 8. 过关自测

1. 为什么 `event_key` 设计比“加更多字段”更关键？  
2. 为什么 bootstrap 必须按插件 topo 顺序恢复？  
3. fingerprint 为什么要包含 settings 和源码 hash？  
4. 为什么 strict read 模式下宁可 409 也不偷偷补算？  
5. 如果线上口径升级，你会怎么解释“为什么只保留最近 N 根重建”？

如果你能把这五题讲清楚，你已经有“可复现系统设计”的核心思维了。
