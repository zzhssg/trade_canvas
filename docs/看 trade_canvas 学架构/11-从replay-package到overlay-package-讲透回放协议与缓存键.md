---
title: 第11关：从 replay package 到 overlay package，讲透回放协议与缓存键
status: done
created: 2026-02-11
updated: 2026-02-11
---

# 第11关：从 replay package 到 overlay package，讲透回放协议与缓存键

这关我们解决一个看起来“只是性能优化”，但本质是**架构正确性**的问题：

**回放（replay）到底该实时点查，还是提前打包缓存？**

如果你只追“快”，很容易出现：

- 这一帧和下一帧口径漂移；
- 前端拖动进度条时读到半状态；
- 同一参数重复请求，每次结果都不一样。

trade_canvas 选的路线是：

**显式构建 + 可复用缓存 + 严格缓存键**。

---

## 0. 先给一句总纲

replay 这条链路的核心不是“把数据塞给前端”，而是三件事同时成立：

1. **时序对齐**：所有数据都对同一个 `aligned_time`。  
2. **包可复用**：同参数命中同一个 `cache_key`。  
3. **包可失效**：底层状态变化后，必须自动换 key，避免脏缓存。

这就是“可复盘系统”与“能跑 demo”最大的分水岭。

---

## 1. 两种包：一个重包讲全量，一个轻包讲绘图

### Replay Package（重包）

`ReplayPackageServiceV1` 产出 SQLite 包（`replay.sqlite`），里面是“全链路回放素材”：

- K 线（`replay_kline_bars`）
- 因子 history 事件（`replay_factor_history_events`）
- 因子 head 快照（`replay_factor_head_snapshots`）
- draw catalog / active checkpoint / diff

它是“可解释回放”的主包。

### Overlay Package（轻包）

`OverlayReplayPackageServiceV1` 产出 JSON 包（`delta_package_full.json`），聚焦绘图层：

- `catalog_base`
- `catalog_patch`
- `checkpoints`
- `diffs`

它是“只关心叠加图层”的轻量包。

一句话：**重包给全景，轻包给画图快进。**

---

## 2. 为什么不是一个包搞定？

因为它们优化目标不同：

- Replay 包要承载“因子可解释性 + draw 一致性 + 窗口重建”，适合 SQLite。  
- Overlay 包只关心前端绘图重建路径，JSON 读起来更直接、调试也更方便。

更关键的是：

`replay_package_builder_v1` 并没有重复造轮子，它直接复用了 `build_overlay_replay_package_v1` 的窗口产物，再写入 SQLite。  
也就是说，底层 draw 语义是同源的，不会出现“两套算法各算各的”。

这就是“功能分层 + 语义复用”。

---

## 3. 回放入口不是 build，而是 prepare + read_only

新手最容易误解：以为 replay 就是 `POST /api/replay/build`。

其实正确入口是：

1. `POST /api/replay/prepare`：先把 `to_time` 对齐到 closed candle，并确保 factor/overlay ledger 到位。  
2. `GET /api/replay/read_only`：只判定“是否可读/是否命中缓存/是否需要构建”，不偷偷计算。  
3. 只有状态是 `build_required` 时，才显式 `POST /api/replay/build`。

这条顺序很工程化：

- `prepare` 负责“口径正确”；
- `read_only` 负责“状态判定”；
- `build` 负责“显式算包”。

职责清晰，就不会出现“一个接口啥都干”的混乱。

---

## 4. `read_only` 的状态机：不是 2 个状态，是 4 个

`ReplayReadOnlyResponseV1.status` 不是简单的 done/build_required，而是：

- `done`：缓存包已存在，直接可读。  
- `build_required`：条件满足但没缓存，允许构建。  
- `coverage_missing`：闭合 K 数量不足，先补覆盖。  
- `out_of_sync`：factor/overlay ledger 还没追到 `to_time`。

这四态非常关键，因为它把“不能读”的原因拆开了：

- 是数据不够（coverage）？
- 还是账本没跟上（out_of_sync）？
- 还是只是没构建（build_required）？

可诊断性直接提升一大截。

---

## 5. 缓存键为什么可靠：把“结果语义”也哈进去

### Replay 包 cache_key

计算 payload 包含：

- 请求参数：`series_id/to_candle_time/window_*`；
- 版本语义：`schema`；
- 数据头部：
  - `candle_store_head_time`
  - `factor_store_last_event_id`
  - `overlay_store_last_version_id`

然后 `stable_json_dumps + sha256`，取前 24 位。

含义非常直接：

- 只改 URL 参数，key 会变；
- 只改底层 ledger（哪怕参数不变），key 也会变。

所以旧缓存不会“误命中新语义”。

### Overlay 包 cache_key

Overlay 包 key 更聚焦：

- 参数 + `overlay_store_last_version_id`。

因为它只服务绘图层，不需要把 factor 事件 id 纳入失效域。

---

## 6. “同一时刻只有一个构建”：BuildJobManager 的单飞保护

两个 service 都用了 `BuildJobManager`：

- `ensure(job_id=cache_key)`：已存在则复用，避免重复起线程；
- `mark_done/mark_error`：统一状态落点。

这就是典型 single-flight：

同一 `cache_key` 的并发构建，不会启动 N 次重活。

同时它还处理了一个实战细节：

如果进程重启，内存里的 job 状态丢了，但磁盘缓存还在，`status` 里会回查 cache 文件，直接返回 `done`。

这让“构建状态”对重启更鲁棒。

---

## 7. coverage 是独立子流程，不混进 build 主流程

`ensure_coverage` 单独一条链路：

- job_id 形如 `coverage_{series_id}:{to_time}:{target_candles}`；
- 先做尾部回补（freqtrade，必要时可走 ccxt）；
- 再 `ingest_pipeline.refresh_series_sync` 推进 ledger；
- 最终 `coverage_status` 报 `candles_ready/required_candles/head_time`。

这说明 replay 团队做了个正确分层：

- coverage 解决“有没有足够闭合 K”；
- build 解决“把现有一致数据打包”。

两个问题不能混成一个“超级 build 接口”。

---

## 8. 前端状态机：不是“拉一次包”，而是“检查 -> 补齐 -> 构建 -> 按窗加载”

`useReplayPackage` 的前端流程很像后端状态机镜像：

1. `read_only` 检查；
2. 若 `coverage_missing`，走 `ensure_coverage + coverage_status` 轮询；
3. 若 `build_required`，触发 `build + status` 轮询；
4. `ready` 后按需 `window(target_idx)` 懒加载窗口。

并且它有双层开关：

- `VITE_ENABLE_REPLAY_V1`（默认代码里是 1）；
- `VITE_ENABLE_REPLAY_PACKAGE_V1`（必须为 1 才启用 package 流程）。

当前 `frontend/.env.development` 没有设置 `VITE_ENABLE_REPLAY_PACKAGE_V1`，所以本地默认仍可退回非 package 路径。

这就是“渐进放量”的前端形态。

---

## 9. 失败语义是显式的，不靠猜

几个典型错误语义：

- `replay.no_data`：连对齐时间都找不到。  
- `replay_prepare.ledger_out_of_sync.*`：prepare 后 ledger 仍没到位。  
- `overlay_replay.ledger_out_of_sync`：overlay 头部没追平。  
- `replay.window.target_idx_out_of_range`：窗口请求越界。

这类 code 化错误非常适合前端状态分流和报警聚合。

记住一句：**错误可分类，系统才可治理。**

---

## 10. 这套设计背后的软件工程范式

- **Read-only 判定与 Compute 解耦**：读接口不隐式算。  
- **Cache Key = 参数 + 数据头部语义**：命中正确，失效正确。  
- **Single-flight 构建**：并发请求不重复消耗。  
- **重包/轻包分层**：同语义，不同性能目标。  
- **开关化上线**：后端 `TRADE_CANVAS_ENABLE_REPLAY_*` + 前端 `VITE_ENABLE_*` 双闸门。

这五条你可以迁移到任何“回放/导出/离线包”系统。

---

## 11. 代码锚点（按时序阅读）

- `backend/app/replay_prepare_service.py`
- `backend/app/replay_routes.py`
- `backend/app/replay_package_service_v1.py`
- `backend/app/replay_package_builder_v1.py`
- `backend/app/replay_package_reader_v1.py`
- `backend/app/overlay_package_service_v1.py`
- `backend/app/overlay_package_builder_v1.py`
- `backend/app/overlay_package_reader_v1.py`
- `backend/app/build_job_manager.py`
- `frontend/src/widgets/chart/useReplayPackage.ts`
- `frontend/src/state/replayStore.ts`
- `backend/tests/test_replay_package_v1.py`
- `backend/tests/test_replay_overlay_package_api.py`
- `backend/tests/test_replay_prepare_service.py`

---

## 12. 过关自测

1. 为什么 replay 的 `read_only` 必须禁止隐式 build？  
2. replay 包 cache_key 为什么要带三种 head（candle/factor/overlay）？  
3. overlay 包 cache_key 为什么只需要 overlay 版本头？  
4. `coverage_missing` 和 `out_of_sync` 的本质区别是什么？  
5. 为什么同一个 `cache_key` 必须 single-flight，而不是允许并发重复 build？

如果你能把这 5 题讲顺，你就不只是“会调 replay 接口”，而是已经掌握了“可复盘系统的缓存治理内核”。
