---
title: 第8关：从 pen 到 zhongshu/anchor——讲透多插件协同状态机
status: done
created: 2026-02-11
updated: 2026-02-11
---

# 第8关：从 pen 到 zhongshu/anchor——讲透多插件协同状态机

上一关你学会了插件架构：每个插件声明依赖，系统自动排序，按拓扑序执行。

但你可能还有一个疑问：**多个插件在同一轮 tick 里，状态到底是怎么"接力"的？**

单看一个插件（比如 pen），逻辑很清晰。但一到多插件联动——pivot 算完传给 pen，pen 算完传给 zhongshu，zhongshu 算完传给 anchor——状态在谁手里？谁先改？谁后读？

这就像一个交响乐团：每个乐手都会自己的乐器，但合奏的时候，谁先起、谁跟进、谁收尾，必须有严格的编排。

这一关，我们把这个"编排"讲透。

---

## 1. 先看全景：一轮 tick 里发生了什么

每来一根 closed 蜡烛，系统做一轮 tick。这一轮里，四个插件按顺序上台：

```text
一轮 tick 的时间线：

  pivot 上台          pen 上台           zhongshu 上台        anchor 上台
  ┌─────────┐      ┌─────────┐       ┌──────────┐        ┌─────────┐
  │找转折点  │  →   │连成笔   │   →   │更新中枢  │    →   │决定锚点 │
  │写:候选点 │      │读:候选点│       │读:新笔   │        │读:入口笔│
  │          │      │写:新笔  │       │写:入口笔 │        │写:切换  │
  └─────────┘      └─────────┘       └──────────┘        └─────────┘
       ↓                ↓                  ↓                   ↓
  major_candidates → new_confirmed   → formed_entries  → anchor.switch
                     _pen_payloads                        事件
```

关键规则：**每个插件只读上游写的字段，只写自己负责的字段。** 就像接力赛：第一棒跑完把棒交出去，第二棒接过来继续跑，不会两个人同时抢一根棒。

---

## 2. 黑板模式：插件不直接对话

插件之间怎么传递数据？不是 A 调用 B 的方法，而是通过一块共享的"黑板"——`FactorTickState`。

想象一间教室的黑板：

- 老师 A 上台，在黑板左边写了几个公式
- 老师 B 上台，看了左边的公式，在右边写了推导过程
- 老师 C 上台，看了右边的推导，在下面写了结论
- 老师 D 上台，看了结论，在角落写了最终答案

每个老师只看自己需要的部分，只写自己负责的部分。没有人直接跟另一个老师说话。

```python
# backend/app/factor_tick_executor.py
@dataclass
class FactorTickState:
    # === 所有人都能看的"教室环境" ===
    visible_time: int                    # 当前处理到哪根蜡烛
    candles: list[Any]                   # 蜡烛数据

    # === pivot 写，pen 读 ===
    major_candidates: list[...]          # 本轮发现的转折点候选

    # === pen 写，zhongshu/anchor 读 ===
    effective_pivots: list[...]          # 有效转折点（跨 tick 传递）
    confirmed_pens: list[dict]           # 已确认的笔（跨 tick 传递）
    new_confirmed_pen_payloads: list[dict]  # 本轮新确认的笔

    # === zhongshu 写，anchor 读 ===
    zhongshu_state: dict                 # 中枢内部状态
    formed_entries: list[dict]           # 本轮形成的中枢入口笔

    # === anchor 读写 ===
    anchor_current_ref: dict | None      # 当前锚点
    anchor_strength: float | None        # 当前锚点强度
```

为什么不让插件直接互相调用？三个原因：

1. **可追踪**：出了 bug，看黑板上的字段就能定位是哪个插件写错了。
2. **可复现**：同样的黑板初始状态 + 同样的执行顺序 = 同样的结果。
3. **可扩展**：新增一个插件，只需要声明"我读哪些字段、写哪些字段"，不用改其他插件的代码。

---

## 3. zhongshu：双触发的中枢状态机

### 问题：中枢只在新笔出现时才变化吗？

不是。zhongshu 有两个触发源，就像一扇门有两把钥匙：

```python
# backend/app/factor_processor_zhongshu.py
def run_tick(self, *, series_id, state, runtime):
    # 钥匙1：新笔触发
    for pen_payload in state.new_confirmed_pen_payloads:
        dead_event, formed_entry = self.update_state_from_pen(
            state=state.zhongshu_state,
            series_id=series_id,
            pen_payload=pen_payload,
        )
        if dead_event is not None:
            state.events.append(dead_event)       # 中枢死了，记一笔
        if formed_entry is not None:
            state.formed_entries.append(formed_entry)  # 中枢入口笔，传给 anchor

    # 钥匙2：K线触发
    idx_now = state.time_to_idx.get(int(state.visible_time))
    if idx_now is None:
        return
    candle = state.candles[int(idx_now)]
    formed_entry_on_candle = self.update_state_from_closed_candle(
        state=state.zhongshu_state,
        candle_time=int(candle.candle_time),
        high=float(candle.high),
        low=float(candle.low),
    )
    if formed_entry_on_candle is not None:
        state.formed_entries.append(formed_entry_on_candle)
```

**钥匙1（新笔触发）**：pen 确认了一笔新的趋势线，zhongshu 检查这笔是否影响中枢——是延伸了中枢？还是突破了中枢让它死亡？

**钥匙2（K线触发）**：即使没有新笔，每根 K 线的价格也可能穿越中枢的边界。这是一条"快速通道"——不用等笔确认，价格穿越就能提前触发中枢形成。

为什么需要两把钥匙？

想象你在监控一个水库的水位：

- **钥匙1**（笔触发）= 每天的水位报告。报告说"水位涨了 5 米"，你更新记录。
- **钥匙2**（K线触发）= 实时水位传感器。即使还没出日报，传感器发现水位超过警戒线了，你也得立刻响应。

两个触发源保证了中枢状态既**准确**（笔确认是权威的）又**及时**（价格穿越不用等）。

### 中枢的生命周期：从 pending 到 alive 到 dead

中枢不是一下子就形成的，它有三个阶段：

```text
pending（待形成）  →  alive（活跃）  →  dead（死亡）
  积累笔，等重叠      价格在区间内震荡    价格突破区间
```

**pending 阶段**：系统积累了几笔，发现它们的价格区间有重叠的趋势，但还不够确认。就像几个人在同一个路口徘徊，你怀疑他们要聚会，但还不确定。

**alive 阶段**：重叠确认了，中枢形成。价格在 `[zd, zg]` 区间内上下震荡。就像聚会开始了，大家在客厅里走来走去。

**dead 阶段**：一笔新的趋势完全在中枢区间外——价格突破了。就像有人推开门走了出去，聚会散了。

```python
# backend/app/zhongshu.py
def _is_same_side_outside(alive, pen):
    """检查笔是否完全在中枢区间外"""
    pen_lo, pen_hi = float(r[0]), float(r[1])
    return pen_hi < float(alive.zd) or pen_lo > float(alive.zg)
    # 完全在下方 或 完全在上方 → 中枢死亡
```

中枢死亡时，系统会：
1. 发出 `zhongshu.dead` 事件（记录这个中枢的一生）
2. 清空状态，准备孕育下一个中枢
3. 用最近的笔尝试构建新的 pending

---

## 4. anchor：双路线的锚点决策

### 问题：交易系统怎么知道"现在该关注哪个信号"？

想象你是一个船长，海上有很多灯塔。你不可能同时盯着所有灯塔——你需要选一个**锚点**（anchor），作为当前的导航参考。

什么时候换锚点？两种情况：

**路线 A：中枢入口笔切换**——你发现了一个新的中枢，中枢的入口笔就是新的锚点。这是"结构性事件"，优先级最高。

**路线 B：强笔切换**——没有新中枢，但出现了一笔特别强的趋势（价格变动幅度大），强到超过了当前锚点的强度。这是"强度竞争"。

```python
# backend/app/factor_processor_anchor.py
def run_tick(self, *, series_id, state, runtime):
    # 路线A：中枢入口笔切换（优先）
    for formed_entry in state.formed_entries:
        switch_event, state.anchor_current_ref, state.anchor_strength = \
            self.apply_zhongshu_entry_switch(
                series_id=series_id,
                formed_entry=formed_entry,
                switch_time=int(state.visible_time),
                old_anchor=state.anchor_current_ref,
            )
        if switch_event is not None:
            state.events.append(switch_event)  # 记录换锚事件

    # 路线B：强笔切换
    # ... 检查候选笔强度是否超过当前锚点 ...
    if state.best_strong_pen_ref is not None:
        switch_event, state.anchor_current_ref, state.anchor_strength = \
            self.apply_strong_pen_switch(
                series_id=series_id,
                switch_time=int(state.visible_time),
                old_anchor=state.anchor_current_ref,
                new_anchor=state.best_strong_pen_ref,
                new_anchor_strength=float(state.best_strong_pen_strength),
            )
        if switch_event is not None:
            state.events.append(switch_event)
```

笔的"强度"怎么算？很直觉——起点价格和终点价格的差值：

```python
# backend/app/factor_pen_contract.py
def pen_strength(payload):
    return abs(float(end_price) - float(start_price))
```

价格变动越大，笔越"强"。一笔从 100 涨到 120 的笔（强度 20），比从 100 涨到 105 的笔（强度 5）更有资格当锚点。

### 换锚的防抖：不是每次都换

不是每个新信号都会触发换锚。系统有一个防抖机制：

```python
# backend/app/anchor_semantics.py
def should_append_switch(*, old_anchor, new_anchor):
    new_id = anchor_pointer_id(new_anchor)
    old_id = anchor_pointer_id(old_anchor)
    if old_id == new_id:
        return False  # 同一个锚点，不换
    return True
```

就像你开车导航：如果新路线和当前路线终点一样，导航不会重新规划。只有真正换了目的地，才会重新导航。

---

## 5. 一个完整的例子：走一轮 tick

假设当前状态：已有一个活跃中枢 `[zd=100, zg=110]`，锚点强度 15。

新来一根 closed 蜡烛，触发一轮 tick：

```text
第①步 pivot：发现一个新的高点 H(115)
  → 写入 major_candidates = [H(115)]

第②步 pen：H(115) 和之前的低点 L(95) 确认了一笔上涨笔
  → 写入 new_confirmed_pen_payloads = [{L→H, direction=1}]
  → 笔强度 = |115 - 95| = 20

第③步 zhongshu：
  钥匙1（笔触发）：新笔 L→H 的区间 [95, 115]
    → 完全包含中枢 [100, 110]？不是。
    → 完全在中枢外？pen_lo=95 < zd=100，但 pen_hi=115 > zg=110
    → 中枢继续延伸，更新 end_time
  钥匙2（K线触发）：当前蜡烛 high=115
    → 没有 pending 结构，跳过

第④步 anchor：
  路线A：没有 formed_entries，跳过
  路线B：笔强度 20 > 当前锚点强度 15
    → 触发强笔切换！发出 anchor.switch 事件
    → 新锚点 = L→H，新强度 = 20
```

一轮 tick，四个插件依次上台，状态像接力棒一样传递。每个插件只看自己需要的字段，只改自己负责的字段。

---

## 6. 为什么这不是"函数调用链"

你可能觉得：这不就是 `pivot() → pen() → zhongshu() → anchor()` 的函数调用吗？

表面上像，但本质不同：

| 维度 | 函数调用链 | 协同状态机 |
| ---- | ---- | ---- |
| 耦合 | A 直接调用 B，A 必须知道 B 的接口 | A 只写黑板，不知道谁会读 |
| 扩展 | 加新步骤要改调用链 | 加新插件只需声明 depends_on |
| 调试 | 要跟踪整个调用栈 | 看黑板快照就能定位 |
| 复现 | 依赖函数内部状态 | 同黑板 + 同顺序 = 同结果 |
| 测试 | 要 mock 整条链 | 构造黑板初始状态即可单测 |

核心区别：函数调用链是"我调你"，协同状态机是"我写黑板，你自己看"。

前者像电话会议——每个人必须知道下一个该打给谁。后者像公告板——你贴上去，需要的人自己来看。

---

## 7. 新增插件的最小步骤

如果你想加一个新因子（比如"风险因子"），依赖 zhongshu 的输出，需要几步？

```python
# 1. 写插件，声明依赖
@dataclass(frozen=True)
class RiskProcessor:
    spec: FactorPluginSpec = FactorPluginSpec(
        factor_name="risk",
        depends_on=("zhongshu",),  # 声明依赖
    )

    def run_tick(self, *, series_id, state, runtime):
        # 读 zhongshu 的产出
        for entry in state.formed_entries:
            # ... 你的风险计算逻辑 ...
            pass
```

```python
# 2. 注册到 manifest
# backend/app/factor_manifest.py
# 把 RiskProcessor 加入 tick_plugins 列表
```

就这两步。你不需要改 pivot、pen、zhongshu、anchor 的任何代码。系统会自动：

- 把 risk 加入 DAG
- 拓扑排序算出新顺序：`pivot → pen → zhongshu → risk → anchor`
- 在每轮 tick 里按新顺序调用

这就是插件架构的威力：**加人不改线**。新工人上流水线，不需要重新设计整条线。

---

## 8. 代码锚点

| 概念 | 文件 | 干什么的 |
| ---- | ---- | ---- |
| 共享黑板 | `backend/app/factor_tick_executor.py` | FactorTickState 定义 |
| zhongshu 插件 | `backend/app/factor_processor_zhongshu.py` | 双触发中枢状态机 |
| 中枢核心算法 | `backend/app/zhongshu.py` | alive/dead/pending 状态转换 |
| anchor 插件 | `backend/app/factor_processor_anchor.py` | 双路线锚点决策 |
| 锚点语义 | `backend/app/anchor_semantics.py` | 换锚防抖逻辑 |
| 笔强度 | `backend/app/factor_pen_contract.py` | pen_strength 计算 |
| 插件注册 | `backend/app/factor_manifest.py` | 写侧/读侧一致性校验 |

---

## 9. 过关自测

如果你能用自己的话回答这五个问题，第 8 关就过了：

1. zhongshu 为什么需要"双触发"（笔触发 + K线触发）？用水库监控的比喻解释。
2. anchor 的两条换锚路线分别是什么？哪条优先级更高？
3. 中枢从 alive 变成 dead 的条件是什么？用聚会散场的比喻解释。
4. 为什么插件之间用"黑板模式"而不是直接互相调用？说出至少两个好处。
5. 如果要新增一个依赖 zhongshu 的插件，最少需要改几个地方？
