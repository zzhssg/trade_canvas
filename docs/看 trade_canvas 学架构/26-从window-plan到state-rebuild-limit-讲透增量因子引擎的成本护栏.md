---
title: 第26关：从 window plan 到 state rebuild limit，讲透增量因子引擎的成本护栏
status: done
created: 2026-02-11
updated: 2026-02-11
---

# 第26关：从 window plan 到 state rebuild limit，讲透增量因子引擎的成本护栏

上一关你学了"失败后怎么安全恢复"。这一关解决另一个生死问题：

**增量计算系统怎么在"结果正确"和"成本可控"之间找到平衡？**

你做因子系统，迟早会撞上一个经典矛盾：

- 你想要"结果正确、可复现"；
- 你又不可能每来一根 K 线就全量重算几万根历史。

想象你在看一部 3 小时的电影。你拖动进度条到 1:30:00，播放器不会从第 1 秒开始解码——它只缓冲前后 30 秒的画面，然后从最近的关键帧开始解码。

增量因子引擎的成本护栏，本质上就是"视频播放器的缓冲策略"：

- **窗口化读取** = 只缓冲前后 30 秒（不加载整部电影）；
- **增量化处理** = 只解码新帧（不重新解码已播放的画面）；
- **版本化重建** = 编码格式升级时只重编最近 1 小时（不重编整部电影）；
- **分层降级** = 网速慢时自动降低清晰度（不卡死在那里）。

---

## 0. 先给一句总纲

增量因子引擎要跑得久、跑得稳，至少要守住 4 条线：

1. **窗口线**：常态只读"够用的局部窗口"；
2. **重建线**：逻辑变更触发重建，但要裁剪历史长度；
3. **回放线**：状态恢复先回放事件，不从零盲算；
4. **扫描线**：历史事件太多时自动切分页扫描，避免一次性爆内存。

这 4 条线在本项目里分别落到了 `factor_ingest_window`、`factor_fingerprint_rebuild`、`factor_rebuild_loader`、`factor_orchestrator`。

---

## 1. 第一幕：窗口不是"拍脑袋长度"，而是按算法算出来的

入口在 `backend/app/factor_ingest_window.py`。

`plan_window(...)` 的窗口长度不是固定常数，而是：

- `lookback_candles = settings_lookback_candles + max_window * 2 + 5`

这里的 `max_window` 来自 major/minor pivot 窗口最大值。

回到播放器比喻：你拖到 1:30:00，播放器不是固定缓冲 30 秒——它会根据视频编码的关键帧间距来决定缓冲多少。关键帧间距大，就多缓冲；间距小，就少缓冲。窗口长度是算出来的，不是猜出来的。

再看起点控制：

- 常态是 `start_time = up_to - lookback * tf_s`；
- 如果已有 `head_time`，还要再做一次 clamp，避免窗口起点越过安全边界。

这就是第一条护栏：

**每次 ingest 只在"局部安全窗口"里工作，不让读取范围无边界膨胀。**

`backend/tests/test_factor_ingest_window.py` 对这套计算有直接断言。

---

## 2. 第二幕：处理集不是"读到的全部"，而是"head 之后到 up_to"

`load_candle_batch(...)` 做了一个常被忽略的拆分：

- `candles`：用于上下文（可包含旧数据）；
- `process_times`：真正需要运行 tick 的时间点。

`process_times` 的定义是：

- `t > head_time`
- 且 `t <= up_to`

继续播放器比喻：缓冲区里可能有 1:29:30 到 1:30:30 的数据，但播放器只解码 1:30:00 之后的新帧——之前的帧已经解码过了，只是作为参考上下文保留。

这背后的范式很重要：

**读上下文和算增量是两件事，必须分离。**

否则你会把"为了看懂现在"误做成"把过去再算一遍"。

---

## 3. 第三幕：逻辑变了怎么办？靠 fingerprint 强制重建，但重建也有上限

入口在 `backend/app/factor_fingerprint_rebuild.py`。

`ensure_series_ready(...)` 的规则是：

- `auto_rebuild=False`：不强制重建；
- `auto_rebuild=True` 且 fingerprint 不同：触发强制重建。

触发后不是粗暴"全删全算"，而是两步：

1. 在 candle 表上 `trim_series_to_latest_n_in_conn`，只保留最近 `keep_candles`；
2. 清空 factor 侧状态并写入新 fingerprint。

回到播放器比喻：视频编码格式从 H.264 升级到 H.265。播放器不会把整部 3 小时电影重新转码——它只重编最近 1 小时的缓存，更早的部分等用户拖到时再按需处理。

这就是第二条护栏：

**允许重建，但重建范围有硬上限（keep_candles）。**

`backend/tests/test_factor_fingerprint_rebuild.py` 直接验证了：

- mismatch 会触发 `forced=True`；
- candle 会被裁到指定长度；
- factor 旧事件被清空；
- debug 里会发 `factor.fingerprint.rebuild`。

---

## 4. 第四幕：为什么"重建状态"优先回放事件，而不是重跑全部逻辑

入口在 `backend/app/factor_rebuild_loader.py`。

`build_incremental_bootstrap_state(...)` 的策略是：

1. 算 `state_start = head_time - lookback * tf_s`；
2. 在这个区间拉历史 factor events；
3. 按 factor 分桶（`events_by_factor`）；
4. 调每个插件 `bootstrap_from_history(...)` 恢复状态。

继续播放器比喻：你暂停了 10 分钟后恢复播放。播放器不会从头开始解码——它找到最近的关键帧，从那里恢复解码状态，然后继续播放新帧。这比"从第 1 帧重新解码"快得多。

这其实是个非常现代的思路：

- 运行态靠增量 tick；
- 恢复态靠事件重放。

恢复成本和事件量相关，而不是和原始行情全量长度强耦合。

---

## 5. 第五幕：历史事件太多时，系统会自动切分页扫描

`collect_rebuild_event_buckets(...)` 先做一次限制扫描：

- `get_events_between_times(..., limit=scan_limit)`

如果命中上限（`rows_truncated=True`），就切到：

- `iter_events_between_times_paged(...)`

同时打 debug 事件 `factor.state_rebuild.limit_reached`。

播放器比喻：网速突然变慢，播放器不会死等整段高清视频下载完——它自动降到 720p 甚至 480p，保证播放不卡顿。等网速恢复了再切回高清。

这就是第三条护栏：

**先快路试探，超阈值自动降级到分页全扫，避免一次 query 吞掉内存。**

`backend/tests/test_factor_orchestrator_settings.py` 有专门回归：命中 limit 后必须走 paged scan。

---

## 6. 第六幕：插件架构如何保证"恢复顺序"和"运行顺序"一致

这一步很多系统会踩坑：

- 运行时按 A→B→C；
- 恢复时按 C→A→B；
- 最终状态就会漂。

trade_canvas 用 `FactorGraph` 统一顺序来源：

- 构图时检查缺失依赖、循环依赖；
- 产出稳定 `topo_order`；
- tick 执行和 bootstrap 都按这个顺序。

`FactorTickExecutor.run_tick_steps(...)` 若插件缺 `run_tick` 会 fail fast（`factor_missing_run_tick:*`）。

播放器比喻：视频有多条轨道（视频轨、音频轨、字幕轨），解码和恢复必须按同一顺序处理。如果恢复时先解码字幕、再解码视频，而播放时反过来，音画就会不同步。

这就是第四条护栏：

**顺序是契约，不是约定。**

---

## 7. 第七幕：持久化层也做了"最小写入"，防止版本噪声

在 `factor_orchestrator._persist_ingest_outputs(...)` 里：

- 事件写入是 append-only，但受唯一键约束；
- head snapshot 只写每个 factor 的当前头；
- head_time 单独 upsert。

这个设计和第 25 关讲的幂等是连起来的：

- 增量流程要快，持久化就不能每次都重写整库；
- 重试要安全，写入就必须可去重、可稳定。

播放器比喻：播放器缓存已解码的帧，但不会每帧都写磁盘——只在关键帧处写一次缓存快照。这样既省 IO，又能从快照快速恢复。

---

## 8. 四条护栏的成本对比

| 护栏 | 没有护栏时 | 有护栏后 | 播放器类比 |
| ------ | ----------- | --------- | ----------- |
| 窗口线 | 每次读全量历史 K 线 | 只读局部窗口 | 只缓冲前后 30 秒 |
| 重建线 | 逻辑变更全量重算 | 裁剪到 keep_candles | 只重编最近 1 小时 |
| 回放线 | 从第一根 K 线重跑 | 从事件回放恢复状态 | 从最近关键帧恢复 |
| 扫描线 | 一次 query 加载全部事件 | 超阈值自动分页 | 网速慢自动降清晰度 |

---

## 9. 这套设计背后的通用方法论

你可以把它迁移成一套"高吞吐增量系统模板"：

1. **窗口化读取**：默认只读局部上下文；
2. **增量化处理**：只处理 head 之后的新点；
3. **版本化重建**：逻辑变更用 fingerprint 驱动；
4. **有界重算**：重建先裁剪历史长度；
5. **分层降级**：超大扫描自动分页。

这套模板不只适合量化因子，日志计算、风控规则、推荐特征链路也通用。

---

## 10. 代码锚点（建议顺读）

- `backend/app/factor_ingest_window.py`
- `backend/app/factor_fingerprint_rebuild.py`
- `backend/app/factor_rebuild_loader.py`
- `backend/app/factor_orchestrator.py`
- `backend/app/factor_tick_executor.py`
- `backend/app/factor_graph.py`
- `backend/tests/test_factor_ingest_window.py`
- `backend/tests/test_factor_fingerprint_rebuild.py`
- `backend/tests/test_factor_orchestrator_settings.py`

---

## 11. 过关自测

1. 为什么窗口长度里要包含 `max_window * 2 + 5` 这类安全余量？
2. `candles` 和 `process_times` 分离，具体帮你避免了什么重复成本？
3. fingerprint mismatch 时，为什么要"裁 candle + 清 factor"，而不是只清 factor？
4. `rows_truncated → paged_scan` 这条降级链解决的根本风险是什么？
5. 你现在项目里有没有"默认全量重算"的路径？它可以套哪一条护栏改成增量？

如果这 5 题你能复述并举例，你已经从"会写算法"进入"会设计可持续运行的算法系统"。
