---
title: 第13关：从 factor slices 到 world frame，讲透读模型一致性
status: done
created: 2026-02-11
updated: 2026-02-11
---

# 第13关：从 factor slices 到 world frame，讲透读模型一致性

前面 6 关你学的全是"怎么写"——蜡烛怎么存、因子怎么算、故障怎么补偿。

这一关反过来：**写完以后，怎么读才不乱？**

你可能觉得"读"有什么难的，不就是 `SELECT * FROM table` 吗？

不是。

想象一个新闻直播间。A 摄像机拍主持人，B 摄像机拍嘉宾。导播台把两路画面合成一个画面输出给观众。如果 A 机位是 14:00:03 的画面，B 机位是 14:00:01 的画面，观众看到的就是一个"物理上不存在的时刻"——主持人在说 3 秒后的话，嘉宾还在回答 1 秒前的问题。

trade_canvas 的读模型面对的就是这个问题：

- 因子（factor）已经算到了第 100 根蜡烛；
- 覆盖层（overlay）还停在第 98 根；
- 前端把两者拼在一起展示，用户看到一幅"物理上不存在的世界"。

这一关的核心能力，就是**杜绝这种"拼接幻觉"**。

---

## 1. 先给一句总纲

读模型一致性的核心不是"读得快"，而是：

**同一个响应里，所有视图必须指向同一根蜡烛（同一个 `candle_id`）。**

守住这条，前端看到的就是一个真实时刻的快照。
守不住，系统宁可返回 409 拒绝服务，也不给你一幅假画面。

就像导播台的铁律：两路画面时间码对不上，宁可黑屏，不上假画面。

---

## 2. 三层读模型：各管各的，最后统一验收

trade_canvas 的读取不是一个大函数，而是三层流水线：

```
第一层                第二层                第三层
FactorReadService → DrawReadService → WorldReadService
（读因子切片）       （读覆盖层增量）     （合并 + 一致性闸门）
```

用直播间的比喻：

- 第一层是 A 机位（因子）：我负责拍主持人，保证我这路画面时间码正确。
- 第二层是 B 机位（覆盖层）：我负责拍嘉宾，保证我这路画面完整。
- 第三层是导播台（世界帧）：我把两路画面合成，但合成前必须验证时间码一致。

为什么要分三层而不是一个函数全包？

因为每层的"正确性标准"不一样：
- 因子层关心的是"口径是否新鲜"（你读到的因子是不是最新算法算出来的）；
- 覆盖层关心的是"增量是否完整"（你拿到的 patch 能不能拼出完整画面）；
- 世界层关心的是"时空是否一致"（两路数据是不是同一根蜡烛的）。

三个不同的问题，三层各自解决，最后统一验收。

---

## 3. 第一层：因子切片——不是"盲读数据库"，而是"带新鲜度的读取"

### 3.1 时间对齐：先把"模糊时间"变成"精确蜡烛"

你请求"给我 14:03:27 的因子数据"，系统不会真的去找 14:03:27。

它会先做 `floor` 对齐：14:03:27 在 5 分钟线上对齐到 14:00:00。

就像你去图书馆找书，你说"我要那本大概在第三排的书"，图书管理员会先帮你定位到"第三排第 7 格"——一个精确的位置。

对齐后的时间生成 `candle_id = "{series_id}:{aligned_time}"`，这就是整个读链路的"时间码"。

### 3.2 事件分桶：把散落的事件归类整理

因子存储里存的是一条条事件（pivot.major、pen.confirmed、zhongshu.dead……），读取时需要把它们按类型归到不同的"桶"里。

```python
# 每个因子插件声明自己需要哪些桶
_PIVOT_BUCKET_SPECS = (
    SliceBucketSpec(
        factor_name="pivot",
        event_kind="pivot.major",
        bucket_name="piv_major",
        sort_keys=("visible_time", "pivot_time"),
    ),
    SliceBucketSpec(
        factor_name="pivot",
        event_kind="pivot.minor",
        bucket_name="piv_minor",
    ),
)
```

就像超市理货员：货架上散落着各种商品，理货员按"饮料""零食""日用品"分别归到不同货架。每个因子插件就是一个理货员，声明"我需要哪几类商品"。

### 3.3 可见性过滤：不是所有事件都能被"看到"

这是因子切片里一个非常精妙的设计。

pivot 的 major 事件有一个 `visible_time` 字段。意思是：这个事件虽然在 T 时刻产生了，但要到 T+N 时刻才"可见"。

```python
def _is_visible_payload(payload, *, at_time):
    vt = payload.get("visible_time")
    if vt is None:
        return True
    return int(vt) <= int(at_time)
```

为什么要这样？

想象你在考试。老师在第 5 分钟出了一道题，但规定"第 10 分钟才能翻开看"。如果你在第 7 分钟就偷看了，那你的答案就不公平。

pivot 的 major 需要等 `window_major` 根蜡烛确认后才算"真的成立"。在确认之前，它虽然已经写入了数据库，但读取时会被 `visible_time` 过滤掉。

这就保证了：**读到的因子状态，和"如果你当时在场会看到的"完全一致。**

### 3.4 拓扑排序构建：后面的插件能看到前面的结果

四个因子插件有依赖关系：

```
pivot → pen → zhongshu → anchor
```

构建快照时严格按拓扑顺序执行。关键在于 `ctx.snapshots`——已经构建好的快照会传给后续插件。

比如 anchor 插件需要从 pen 的快照里读取候选锚点：

```python
# AnchorSlicePlugin.build_snapshot
pen_slice = ctx.snapshots.get("pen")
if pen_slice is not None:
    pen_head_candidate = (pen_slice.head or {}).get("candidate")
```

就像流水线上的工人：第一个工人做好零件 A，放在传送带上；第二个工人拿到零件 A，加工成零件 B；第三个工人拿到 A 和 B，组装成成品。每个工人只关心"传送带上有没有我需要的零件"。

### 3.5 新鲜度检查：读之前先问"口径还对不对"

`FactorReadService` 在读取前会检查因子的"新鲜度"：

- **非 strict 模式**：如果因子 head 落后于请求时间，系统会自动尝试 `ingest_closed` 追平。就像你去餐厅点菜，厨师发现食材不够新鲜，先去后厨补一批再上菜。
- **strict 模式**：如果因子 head 落后，直接返回 409（`ledger_out_of_sync:factor`）。就像你去米其林餐厅，食材不够新鲜？对不起，今天这道菜不供应。

---

## 4. 第二层：覆盖层增量——不是"能给就给"，而是"先保证站得住"

### 4.1 增量读取：用 cursor 代替全量刷新

覆盖层的读取是增量的。前端第一次请求拿到完整数据（cursor=0），之后每次只拿"上次之后的变化"。

就像订报纸：第一天给你一份完整的报纸，之后每天只给你"号外"——只有新消息。

### 4.2 首包完整性校验：第一份报纸必须是完整的

当 cursor=0（首次请求）时，`DrawReadService` 会做一次完整性校验：

调用 `evaluate_overlay_integrity` 对比因子切片和覆盖层定义是否匹配。

为什么？因为如果因子刚被重建过（fingerprint 变了），覆盖层可能还是旧口径的数据。这时候给你一份"新因子 + 旧覆盖层"的数据，就像给你一份"今天的头条 + 昨天的天气预报"的报纸——看起来完整，其实自相矛盾。

不一致时，系统拒绝返回，要求先 repair。

### 4.3 overlay head 守卫

覆盖层也有自己的 head（最新处理到哪根蜡烛）。如果 overlay head 落后于请求时间，直接 409（`ledger_out_of_sync:overlay`）。

两层各自守自己的底线：因子守因子的新鲜度，覆盖层守覆盖层的完整性。

---

## 5. 第三层：世界帧——导播台的"时间码闸门"

### 5.1 核心一刀：强制 candle_id 一致

`WorldReadService` 把因子切片和覆盖层增量合并成一个"世界帧"。但合并前，它会做全链路最关键的一次校验：

```
factor_slices.candle_id == draw_state.to_candle_id == "{series_id}:{aligned_time}"
```

三个值必须完全相等。任何一个不等，直接 409。

这就是导播台的铁律：A 机位时间码 14:00:00，B 机位时间码 14:00:00，导播台期望 14:00:00。三者一致才上屏。

为什么第三层还要再验一次？前两层不是各自验过了吗？

因为前两层各自验的是"我自己对不对"，第三层验的是"你们俩对不对齐"。A 机位画面清晰（因子新鲜），B 机位画面完整（覆盖层完整），但如果 A 拍的是 14:00 而 B 拍的是 13:59，合在一起还是假的。

### 5.2 两种读取方式：直播 vs 回放

```python
# 直播模式：给你"当前最安全的公共交集时刻"
def read_frame_live(self, series_id):
    # 取 market head 和 overlay head 的较小值
    # 再 floor 到有效 candle
    # 构建当前可读世界帧

# 回放模式：给你"历史定点回看"
def read_frame_at_time(self, series_id, at_time):
    # 直接按 at_time 对齐
    # 构建该时刻世界帧
```

直播模式就像看实况转播——导播台给你"当前所有机位都准备好的最新画面"。
回放模式就像看录像回放——你指定一个时间点，导播台给你那个时刻的画面。

两者复用同一个一致性闸门，不会因为入口不同就放松标准。

### 5.3 增量轮询：有变化才推送

`poll_delta(after_id)` 的逻辑：

1. 先查覆盖层有没有新版本（cursor 之后有没有新数据）；
2. 没有新版本 → 返回空 records；
3. 有新版本 → 返回一条包含 draw_delta + factor_slices 的 world record。

这带来三个工程收益：

- **省带宽**：没变化就不传数据，天然节流。
- **可恢复**：cursor 是显式协议，断线重连从上次位置继续。
- **不丢不重**：每条 record 有明确的 cursor 标识。

就像微信聊天：你不在线时消息存着，上线后从"上次已读"位置开始推送，不会重复也不会遗漏。

---

## 6. 因子切片的完整构建流程（走一遍）

假设前端请求 `BTCUSDT:1h` 在 `at_time=1707012345` 的因子切片：

```
第①步：时间对齐
  at_time=1707012345 → floor 到 1h → aligned_time=1707012000
  candle_id = "BTCUSDT:1h:1707012000"

第②步：计算窗口
  window_candles=2000, tf_s=3600
  start_time = 1707012000 - 2000*3600 = 1699812000

第③步：读取事件
  从 factor_store 读取 [1699812000, 1707012000] 范围内的所有事件

第④步：事件分桶
  pivot.major → piv_major 桶（按 visible_time, pivot_time 排序）
  pivot.minor → piv_minor 桶
  pen.confirmed → pen_confirmed 桶（按 visible_time, start_time 排序）
  zhongshu.dead → zhongshu_dead 桶
  anchor.switch → anchor_switches 桶

第⑤步：可见性过滤
  每个桶里的事件，只保留 visible_time <= 1707012000 的

第⑥步：读取头部快照
  为 pivot/pen/zhongshu/anchor 各读一个 head_at_or_before(1707012000)

第⑦步：拓扑构建
  PivotSlicePlugin.build_snapshot → 用 piv_major + piv_minor 构建 pivot 快照
  PenSlicePlugin.build_snapshot   → 用 pen_confirmed + head 构建 pen 快照
  ZhongshuSlicePlugin.build_snapshot → 用 pen_confirmed + candles 重建 alive 头部
  AnchorSlicePlugin.build_snapshot → 从 pen 快照读候选锚点，计算最优锚点

第⑧步：组装响应
  返回 GetFactorSlicesResponseV1(
    candle_id="BTCUSDT:1h:1707012000",
    factors=["pivot", "pen", "zhongshu", "anchor"],
    snapshots={...}
  )
```

整个过程的关键：**所有数据都锚定在同一个 `aligned_time`，所有事件都经过 `visible_time` 过滤。**

---

## 7. 这套设计背后的四条工程原则

```
原则1：Fail closed（不一致就拒绝）
  → 宁可返回 409，不返回拼接假象
  → 就像导播台宁可黑屏，不上错位画面

原则2：Alignment first（先对齐，再谈内容）
  → 所有读取的第一步都是时间对齐
  → 就像所有机位先对时间码，再开始拍摄

原则3：Composable reads（分域读取，统一闸门）
  → 因子、覆盖层各自保证自己的正确性
  → 世界帧在合并时做最终一致性校验
  → 就像每个机位各自调焦，导播台统一验收

原则4：Cursor over snapshot spam（增量优于全量）
  → 用 cursor 协议控制读压与状态同步
  → 就像微信的"已读位置"，不用每次重传所有消息
```

这四条原则不只适用于量化交易。任何需要"多数据源合成一个视图"的系统——仪表盘、监控大屏、协同编辑——都能用。

---

## 8. 代码锚点（按阅读顺序）

| 概念 | 文件 | 干什么的 |
| ---- | ---- | ---- |
| 因子切片服务 | `backend/app/factor_slices_service.py` | 事件分桶 + 可见性过滤 + 拓扑构建 |
| 切片插件契约 | `backend/app/factor_slice_plugin_contract.py` | FactorSliceBuildContext 定义 |
| 四个切片插件 | `backend/app/factor_slice_plugins.py` | pivot/pen/zhongshu/anchor 各自的构建逻辑 |
| 因子读服务 | `backend/app/read_models/factor_read_service.py` | 新鲜度检查 + strict/non-strict |
| 覆盖层读服务 | `backend/app/read_models/draw_read_service.py` | 增量读取 + 首包完整性校验 |
| 世界帧读服务 | `backend/app/read_models/world_read_service.py` | candle_id 一致性闸门 |
| 新鲜度检查 | `backend/app/factor_read_freshness.py` | ledger head 对比 |
| 数据模型 | `backend/app/schemas.py` | FactorSliceV1 / GetFactorSlicesResponseV1 |

---

## 9. 过关自测

1. 为什么世界帧层还要再做一次 `candle_id` 一致性校验？前两层不是各自验过了吗？
2. `visible_time` 过滤解决的是什么问题？如果去掉会怎样？
3. 非 strict 和 strict 模式在因子读取上有什么语义差异？各适合什么场景？
4. 为什么覆盖层首包（cursor=0）需要完整性校验而不是直接放行？
5. 如果前端出现"图线和信号错位"，你会按什么顺序排查三层读模型？

能把这 5 题用自己的话讲清楚，你就掌握了"读模型一致性"的核心思维——不是"读得到"就行，而是"读到的必须是同一个真实时刻的快照"。
