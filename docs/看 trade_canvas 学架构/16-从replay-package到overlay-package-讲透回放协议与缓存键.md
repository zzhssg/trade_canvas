---
title: 第16关：从 replay package 到 overlay package，讲透回放协议与缓存键
status: done
created: 2026-02-11
updated: 2026-02-11
---

# 第16关：从 replay package 到 overlay package，讲透回放协议与缓存键

前面你学了实时数据怎么推、怎么补、怎么对齐。

但量化交易有一个核心需求是"回放"——我想看昨天下午3点到5点，BTCUSDT 1小时线上发生了什么。因子怎么算的？覆盖层怎么画的？每一步都要能复现。

这就像看足球比赛录像。你不是要看"现在的比分"，而是要看"第38分钟那个进球是怎么发生的"。

问题来了：

- 你拖动进度条到38分钟，看到的数据是38分钟时的真实状态，还是"现在的状态混了38分钟的画面"？
- 你暂停再播放，数据会不会变？
- 两个人同时看同一段录像，看到的是不是一样的？

如果这三个问题有一个答不上来，你的"回放"就是假的。

---

## 1. 先给一句总纲

回放不是"把数据塞给前端"，而是三件事同时成立：

1. **时序对齐**：所有数据都对同一个 `aligned_time`，不会出现"K线是3点的，因子是4点的"。
2. **包可复用**：同样的参数，命中同一个缓存包，不重复计算。
3. **包可失效**：底层数据变了，缓存自动作废，不会读到过期录像。

这就是"可复盘系统"和"能跑 demo"的分水岭。

---

## 2. 两种包：重包给全景，轻包给画图

想象你要复盘一场足球比赛。

**重包（Replay Package）** 就像完整的比赛录像——有每一分钟的比分、每个球员的跑位、每次犯规的判罚、教练的战术板。什么都有，但文件很大。

**轻包（Overlay Package）** 就像战术分析剪辑——只有关键进球的回放和战术板标注。轻便快速，但只够看"画了什么"。

在代码里：

```python
# 重包：SQLite 文件，10张表，全链路素材
# backend/app/replay_package_builder_v1.py
replay_meta                    # 包的元数据
replay_kline_bars              # K线数据
replay_window_meta             # 窗口索引
replay_factor_history_events   # 因子历史事件
replay_factor_head_snapshots   # 因子头部快照
replay_factor_history_deltas   # 因子增量索引
replay_draw_catalog_versions   # 绘图目录版本
replay_draw_catalog_window     # 绘图窗口映射
replay_draw_active_checkpoints # 绘图活跃检查点
replay_draw_active_diffs       # 绘图活跃增量
```

```python
# 轻包：JSON 文件，只有绘图层
# backend/app/overlay_package_builder_v1.py
{
    "catalog_base": [...],      # 基础目录
    "catalog_patch": [...],     # 目录补丁
    "checkpoints": [...],       # 检查点快照
    "diffs": [...]              # 增量差异
}
```

为什么不用一个包搞定？因为它们服务不同的人：

- 重包服务"我要理解因子是怎么算的"——需要 K线 + 因子事件 + 绘图，适合用 SQLite 存储（支持 SQL 查询）。
- 轻包服务"我只想快速重建画面"——只需要绘图层，JSON 更轻便。

更关键的是，重包不是另起炉灶。它直接复用了轻包的绘图产物：

```python
# backend/app/replay_package_builder_v1.py
overlay_pkg = build_overlay_replay_package_v1(
    candle_store=candle_store,
    overlay_store=overlay_store,
    params=OverlayReplayBuildParamsV1(...),
)
# 然后把 overlay_pkg 的结果写入 SQLite
```

就像完整录像里的战术板画面，直接从战术分析剪辑里拿，不会出现"两套剪辑各剪各的"。

---

## 3. 回放的正确入口：不是直接 build，而是三步走

新手最容易犯的错：以为回放就是调一个 `POST /api/replay/build`。

错。正确流程是三步：

```text
第①步 prepare     →  "我想看这个时间点，帮我对齐"
第②步 read_only   →  "对齐好了，缓存有没有？能不能读？"
第③步 build       →  "没缓存，那就算一个"
```

这就像去图书馆借书：

1. **prepare**（查目录）：你说"我要借《三体》"，图书管理员先查目录确认有这本书、在哪个架子上。
2. **read_only**（看状态）：管理员告诉你"书在架上可以借" / "书被人借走了" / "这本书我们没有"。
3. **build**（调书）：只有确认"书在但没上架"时，才去仓库把书搬出来。

为什么不能一步到位？

因为 `build` 是重操作——要读 K线、算因子、打包 SQLite。如果每次请求都无脑 build，10个人同时看同一段录像，就要算10次。

---

## 4. read_only 的四态状态机：不是"有没有"，是"为什么没有"

`read_only` 接口不是简单返回"有缓存/没缓存"。它返回四种状态：

```text
done             →  缓存包已存在，直接可读
build_required   →  条件满足但没缓存，可以构建
coverage_missing →  闭合K线数量不够，先补数据
out_of_sync      →  因子/覆盖层账本还没追到目标时间
```

为什么要分这么细？

想象你去餐厅点菜，服务员说"没有"。你会问：

- 是今天没进货（coverage_missing）？→ 等进货
- 是厨师还没做好（out_of_sync）？→ 等一会儿
- 是菜单上有但没人点过（build_required）？→ 现做
- 是已经做好了（done）？→ 直接上

如果服务员只说"没有"，你完全不知道该等还是该换。

看代码里怎么判定的：

```python
# backend/app/replay_package_service_v1.py
def read_only(self, *, series_id, to_time, ...):
    to_candle_time = self._resolve_to_time(series_id, to_time)

    # 第一关：K线够不够？
    coverage = self._coverage(series_id=series_id, to_time=to_candle_time, target_candles=wc)
    if coverage.candles_ready < wc:
        return ("coverage_missing", ...)

    # 第二关：账本追上了没？
    factor_head = self._factor_store.head_time(series_id)
    overlay_head = self._overlay_store.head_time(series_id)
    if factor_head < to_candle_time or overlay_head < to_candle_time:
        return ("out_of_sync", ...)

    # 第三关：缓存有没有？
    cache_key = self._compute_cache_key(...)
    if self.cache_exists(cache_key):
        return ("done", ...)
    else:
        return ("build_required", ...)
```

注意判定顺序：先查数据够不够，再查账本同步没，最后查缓存。这个顺序不能乱——如果数据都不够，算出来的缓存也是错的。

---

## 5. 缓存键的设计：为什么同样的参数，换了数据就要换钥匙

这是本关最值钱的设计。

普通缓存键长这样：`hash(series_id + to_time + window_size)`。参数一样，key 一样，命中缓存。

但这有个致命问题：**底层数据变了，参数没变，缓存还是旧的。**

就像你用"2026年2月BTCUSDT月报"当文件名。2月还没过完，你写了一版。2月底数据更新了，文件名没变，但内容该变了。如果还用旧文件，报告就是错的。

trade_canvas 的解决方案：**把数据的"版本头"也哈进缓存键。**

```python
# backend/app/replay_package_service_v1.py
def _compute_cache_key(self, *, series_id, to_time, ...):
    payload = {
        "schema": "replay_package_v1",
        "series_id": series_id,
        "to_candle_time": int(to_time),
        "window_candles": int(window_candles),
        # ↓ 这三个是关键：数据版本头
        "candle_store_head_time": int(self._candle_store.head_time(series_id) or 0),
        "factor_store_last_event_id": int(self._factor_store.last_event_id(series_id)),
        "overlay_store_last_version_id": int(self._overlay_store.last_version_id(series_id)),
    }
    h = stable_json_dumps(payload)
    return sha256(h)[:24]
```

三个版本头各管一摊：

| 版本头 | 含义 | 什么时候变 |
| ---- | ---- | ---- |
| `candle_store_head_time` | K线仓库最新时间 | 新K线入库 |
| `factor_store_last_event_id` | 因子仓库最新事件ID | 因子重算或新算 |
| `overlay_store_last_version_id` | 覆盖层仓库最新版本ID | 覆盖层更新 |

效果：

- 参数不变，数据不变 → key 不变 → 命中缓存 ✅
- 参数不变，K线多了一根 → key 变了 → 旧缓存自动作废 ✅
- 参数不变，因子重算了 → key 变了 → 旧缓存自动作废 ✅

**缓存永远不会"误命中旧语义"。**

### 轻包的缓存键更简单

Overlay 轻包只关心绘图层，所以它的缓存键只带一个版本头：

```python
# backend/app/overlay_package_service_v1.py
def _compute_cache_key(self, series_id, *, to_time, ...):
    payload = {
        "schema": "overlay_replay_package_v1",
        "series_id": series_id,
        "to_candle_time": int(to_time),
        # ↓ 只需要覆盖层版本
        "overlay_store_last_version_id": int(self._overlay_store.last_version_id(series_id)),
    }
```

为什么不带 K线和因子的版本头？因为轻包里没有 K线和因子数据，它们变不变跟轻包无关。

就像战术分析剪辑不关心"球员体检报告有没有更新"——那是完整录像的事。

---

## 6. 单飞保护：10个人同时看，只算一次

假设10个用户同时请求同一段回放。如果每个请求都触发一次 build，就要算10次完全相同的包。浪费。

`BuildJobManager` 解决这个问题：

```python
# backend/app/build_job_manager.py
class BuildJobManager:
    def ensure(self, *, job_id, cache_key) -> tuple[BuildJob, bool]:
        with self._lock:
            existing = self._jobs.get(job_id)
            if existing is not None:
                return (existing.to_view(), False)  # 已有任务，复用
            created = _BuildJobState(
                job_id=job_id,
                cache_key=cache_key,
                status="building",
                started_at_ms=now_ms,
            )
            self._jobs[job_id] = created
            return (created.to_view(), True)  # 新建任务
```

`ensure` 返回一个元组 `(job, is_new)`：

- `is_new=True`：你是第一个请求，去干活。
- `is_new=False`：已经有人在算了，等着就行。

这就是"单飞"（single-flight）模式。就像食堂打饭：10个人都要红烧肉，厨师只炒一锅，不会炒10锅。

还有一个实战细节：如果服务重启了，内存里的 job 状态丢了，但磁盘上的缓存文件还在。`status` 查询时会先检查磁盘缓存，如果文件存在就直接返回 `done`。

就像你重启了电脑，但硬盘上的文件还在——不需要重新下载。

---

## 7. coverage 是独立子流程：先确认"原材料够不够"

回放需要足够的闭合K线作为原材料。如果你要看最近2000根K线的回放，但仓库里只有1500根，那就得先补齐。

这个"补齐"操作叫 `ensure_coverage`，它是一条独立的子流程，不混进 build 主流程。

为什么要分开？

想象你要做一桌菜。"买菜"和"炒菜"是两件事：

- **买菜（coverage）**：确认冰箱里有没有足够的食材。没有就去超市买。
- **炒菜（build）**：食材齐了，开始做菜。

如果把"买菜"和"炒菜"混成一个函数，会出现：

- 你不知道"做菜失败"是因为"没食材"还是"炒糊了"。
- 你没法单独重试"买菜"而不重新"炒菜"。

coverage 子流程的 job_id 也很讲究：

```text
coverage_{series_id}:{to_time}:{target_candles}
```

同样的补齐请求不会重复执行（也是单飞）。补齐完成后，`coverage_status` 会报告：

- `candles_ready`：现在有多少根
- `required_candles`：需要多少根
- `head_time`：最新一根的时间

---

## 8. 窗口化加载：不是一次全给，而是按需切片

一个回放包可能有2000根K线。如果一次性全发给前端，数据量太大，页面会卡。

所以系统把回放包切成"窗口"（window），每个窗口500根K线：

```text
窗口0: K线 0~499
窗口1: K线 500~999
窗口2: K线 1000~1499
窗口3: K线 1500~1999
```

前端拖动进度条时，只加载当前窗口的数据：

```text
GET /api/replay/window?cache_key=abc123&target_idx=750
→ 返回窗口1的数据（包含 K线500~999 + 对应的因子快照 + 绘图状态）
```

`target_idx` 是"我想看第几根K线"，系统自动算出它属于哪个窗口。

这就像视频网站的分段加载：你拖到第38分钟，它只加载38分钟附近的片段，不会把整场比赛都下载下来。

每个窗口里不只有K线，还有：

- **因子头部快照**：这个窗口起点时，每个因子的状态是什么。
- **绘图检查点**：这个窗口起点时，画面上有哪些图形。
- **绘图增量**：从窗口起点到终点，图形怎么变化的。

有了这些，前端可以从任意窗口开始播放，不需要从头算起。

---

## 9. 前端状态机：镜像后端的四态

前端的 `useReplayPackage` 不是"调一次接口就完事"，而是一个状态机，镜像后端的四态：

```text
① read_only 检查
   ├─ done → 直接用缓存包
   ├─ build_required → 触发 build，轮询 status
   ├─ coverage_missing → 触发 ensure_coverage，轮询 coverage_status
   └─ out_of_sync → 等待，稍后重试

② build 完成后 → 按需 window(target_idx) 懒加载

③ 用户拖动进度条 → 计算新的 target_idx → 加载对应窗口
```

并且前端有双层开关：

- `VITE_ENABLE_REPLAY_V1`：回放功能总开关。
- `VITE_ENABLE_REPLAY_PACKAGE_V1`：package 流程开关（必须为1才走打包路径）。

如果 package 开关没开，前端退回到非 package 的实时查询路径。这就是"渐进放量"——新功能先在小范围验证，确认没问题再全量放开。

---

## 10. 错误语义是显式的：不靠猜，靠编码

回放链路的错误不是一句"失败了"，而是精确的错误码：

```text
replay.no_data                              → 连对齐时间都找不到
replay_prepare.ledger_out_of_sync.factor    → prepare 后因子账本没追上
replay_prepare.ledger_out_of_sync.overlay   → prepare 后覆盖层账本没追上
overlay_replay.ledger_out_of_sync           → overlay 头部没追平
replay.window.target_idx_out_of_range       → 窗口请求越界
```

每个错误码都是"域.动作.原因"的三段式。前端拿到错误码，可以精确地走不同的处理分支：

- `no_data` → 提示"没有数据"
- `ledger_out_of_sync` → 提示"数据还在同步，请稍候"
- `target_idx_out_of_range` → 提示"超出范围"

记住一句：**错误可分类，系统才可治理。**

---

## 11. 一个完整的回放场景走一遍

假设用户要回放 BTCUSDT 1小时线，看到2026年2月10日下午3点的状态。

```text
① 前端调 POST /api/replay/prepare
   → series_id="BTCUSDT:1h", to_time=1707566400
   → 后端对齐到最近的闭合K线时间
   → 返回 aligned_time=1707566400

② 前端调 GET /api/replay/read_only
   → 后端检查：
     - K线够不够？2000根 ✅
     - 因子账本追上了？head_time >= 1707566400 ✅
     - 覆盖层追上了？head_time >= 1707566400 ✅
     - 缓存有没有？没有
   → 返回 status="build_required", cache_key="a1b2c3..."

③ 前端调 POST /api/replay/build
   → BuildJobManager.ensure(job_id="a1b2c3...")
   → is_new=True，开始构建
   → 读K线、算因子快照、打包绘图层、写入 SQLite
   → mark_done

④ 前端轮询 GET /api/replay/status
   → status="done"

⑤ 前端调 GET /api/replay/window?target_idx=0
   → 返回窗口0：K线0~499 + 因子快照 + 绘图检查点

⑥ 用户拖动进度条到第1200根
   → 前端调 GET /api/replay/window?target_idx=1200
   → 返回窗口2：K线1000~1499 + 对应快照
```

整个过程：对齐 → 判定 → 构建 → 按窗加载。每一步职责清晰，每一步都可以单独重试。

---

## 12. 这套设计背后的五条工程原则

```text
原则1：Read-only 判定与 Compute 解耦
  → 读接口不偷偷算。"看状态"和"做计算"是两个动作
  → 就像医生"看诊"和"做手术"必须分开

原则2：Cache Key = 参数 + 数据版本头
  → 参数一样但数据变了，key 也变
  → 缓存命中正确，失效也正确

原则3：Single-flight 构建
  → 同一个 cache_key 的并发请求，只算一次
  → 10个人看同一段录像，厨师只做一份

原则4：重包/轻包分层
  → 同一套底层语义，不同的性能目标
  → 完整录像和战术剪辑共享同一个素材库

原则5：开关化上线
  → 后端 TRADE_CANVAS_ENABLE_REPLAY_* + 前端 VITE_ENABLE_*
  → 新功能先小范围验证，确认安全再全量放开
```

这五条你可以迁移到任何"回放/导出/离线包"系统。

---

## 13. 代码锚点（按阅读顺序）

| 概念 | 文件 | 干什么的 |
| ---- | ---- | ---- |
| 回放准备 | `backend/app/replay_prepare_service.py` | 时间对齐 + ledger 追平 |
| 回放路由 | `backend/app/replay_routes.py` | 7个 API 端点 |
| 重包服务 | `backend/app/replay_package_service_v1.py` | read_only/build/status/window |
| 重包构建 | `backend/app/replay_package_builder_v1.py` | SQLite 10表 schema + 打包 |
| 重包读取 | `backend/app/replay_package_reader_v1.py` | 窗口切片 + 元数据读取 |
| 轻包服务 | `backend/app/overlay_package_service_v1.py` | overlay 专用缓存包 |
| 轻包构建 | `backend/app/overlay_package_builder_v1.py` | JSON 打包 |
| 单飞管理 | `backend/app/build_job_manager.py` | ensure/mark_done/mark_error |
| 前端回放 | `frontend/src/widgets/chart/useReplayPackage.ts` | 前端状态机 |
| 前端状态 | `frontend/src/state/replayStore.ts` | 回放状态管理 |

---

## 14. 过关自测

1. 为什么 `read_only` 必须禁止隐式 build？用"图书馆借书"的比喻解释。
2. replay 包的 cache_key 为什么要带三个版本头（candle/factor/overlay）？如果只带参数会怎样？
3. overlay 包的 cache_key 为什么只需要 overlay 版本头？它和 replay 包的区别是什么？
4. `coverage_missing` 和 `out_of_sync` 的本质区别是什么？用"做菜"的比喻解释。
5. 为什么同一个 cache_key 必须 single-flight，而不是允许并发重复 build？

能把这5题讲清楚，你就不只是"会调回放接口"，而是掌握了"可复盘系统的缓存治理内核"。
