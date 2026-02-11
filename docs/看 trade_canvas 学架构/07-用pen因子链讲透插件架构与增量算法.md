---
title: 第7关：用 pen 因子链讲透插件架构与增量算法
status: done
created: 2026-02-11
updated: 2026-02-11
---

# 第7关：用 pen 因子链讲透插件架构与增量算法

上一关你学会了缠论的三层结构：pivot 找山顶山谷，pen 连成趋势线，zhongshu 圈出震荡区。

但你有没有想过一个问题：**这三层算法，代码里是怎么组织的？**

如果你把 pivot、pen、zhongshu 的代码全写在一个大函数里，会怎样？

```python
# 千万别这么写
def calculate_everything(candles):
    pivots = find_pivots(candles)
    pens = find_pens(pivots)
    zhongshus = find_zhongshus(pens)
    return pivots, pens, zhongshus
```

看起来很简洁？但问题马上来了：

- 想加一个新因子（比如 anchor），你得改这个函数。
- 想调整 pen 的算法，你得小心别碰坏 zhongshu。
- 想单独测试 pivot，你得把整个函数跑一遍。
- 想让 pen 和 zhongshu 并行开发，两个人会不停冲突。

一个函数变成了一锅粥。

这一关，我们用 pen 因子链作为切口，讲透两个核心设计：**插件架构**（怎么把一锅粥拆成流水线）和**增量算法**（怎么不重复劳动）。

---

## 1. 插件架构：从一锅粥到流水线

### 问题：怎么让每个算法各干各的，又能协作？

想象一家汽车工厂。

如果让一个工人从头到尾造一辆车——焊车架、装发动机、喷漆、装轮胎——效率极低，而且这个工人得会所有工种。

现代工厂的做法是**流水线**：每个工位只干一件事，干完把半成品传给下一个工位。

```text
工位1(焊接)  →  工位2(发动机)  →  工位3(喷漆)  →  工位4(轮胎)
   ↓               ↓                ↓              ↓
  车架            动力总成          涂装            成品车
```

这个系统的因子计算就是这样的流水线：

```text
工位1(pivot)  →  工位2(pen)  →  工位3(zhongshu)  →  工位4(anchor)
   ↓                ↓              ↓                  ↓
  转折点            趋势笔          震荡中枢            锚点信号
```

每个"工位"就是一个**插件**（Plugin）。

### 插件的"身份证"：FactorPluginSpec

每个插件上岗前，要先填一张"身份证"，声明两件事：

1. **我叫什么**（factor_name）
2. **我需要谁先干完**（depends_on）

```python
# backend/app/factor_plugin_contract.py
@dataclass(frozen=True)
class FactorPluginSpec:
    factor_name: str                    # 我叫什么
    depends_on: tuple[str, ...] = ()    # 我需要谁先干完
```

看看真实的插件怎么填这张身份证：

```python
# backend/app/factor_processor_pivot.py
@dataclass(frozen=True)
class PivotProcessor:
    spec: FactorPluginSpec = FactorPluginSpec(
        factor_name="pivot",
        depends_on=(),          # 空！我不依赖任何人，我是第一道工序
    )
```

```python
# backend/app/factor_processor_pen.py
@dataclass(frozen=True)
class PenProcessor:
    spec: FactorPluginSpec = FactorPluginSpec(
        factor_name="pen",
        depends_on=("pivot",),  # 我需要 pivot 先算完
    )
```

```python
# backend/app/factor_processor_zhongshu.py
@dataclass(frozen=True)
class ZhongshuProcessor:
    spec: FactorPluginSpec = FactorPluginSpec(
        factor_name="zhongshu",
        depends_on=("pen",),    # 我需要 pen 先算完
    )
```

注意 `depends_on` 的写法——它不是说"请在我之前调用 pivot"，而是说"我**需要** pivot 的产出"。这个区别很重要：你声明的是**需求**，不是**顺序**。顺序由系统自动推导。

就像大学选课：你不是说"我要在周一上高数"，而是说"我选数据结构，它的前置课是高数"。教务系统会自动帮你排出合理的课表。

---

## 2. 拓扑排序：让系统自动排课表

### 问题：有了依赖声明，怎么算出执行顺序？

四个插件的依赖关系：

```text
pivot (无依赖)
  ↓
pen (依赖 pivot)
  ↓
zhongshu (依赖 pen)
  ↓
anchor (依赖 pen, zhongshu)
```

这是一个 DAG（有向无环图）。系统用**拓扑排序**算出执行顺序：

```python
# backend/app/factor_graph.py
class FactorGraph:
    def _toposort(self) -> tuple[str, ...]:
        # DFS 后序遍历：先递归处理依赖，再处理自己
        visiting: set[str] = set()
        visited: set[str] = set()
        order: list[str] = []

        def dfs(n: str) -> None:
            if n in visited:
                return
            if n in visiting:
                raise FactorGraphError(f"cycle:{'->'.join(...)}")  # 检测到环！
            visiting.add(n)
            deps = sorted(self._by_name[n].depends_on)  # 排序保证稳定
            for d in deps:
                dfs(d)
            visited.add(n)
            order.append(n)

        for name in sorted(self._by_name.keys()):  # 排序保证稳定
            dfs(name)
        return tuple(order)
```

排出来的结果：`("pivot", "pen", "zhongshu", "anchor")`。

注意两个 `sorted()` 调用——它们保证了**稳定性**：不管你以什么顺序注册插件，排出来的课表永远一样。这就是第 1 关讲的铁律"同输入同输出"。

### 三道安全门

拓扑排序之前，系统还会做三道检查：

| 检查 | 白话 | 后果 |
|------|------|------|
| 重名检测 | 两个工人叫同一个名字 | 直接报错，不让上岗 |
| 缺依赖检测 | pen 说"我需要 pivot"，但 pivot 没注册 | 直接报错，不开工 |
| 环检测 | A 依赖 B，B 依赖 A，死锁了 | 直接报错，报告环路径 |

这三道门都是在**启动时**检查的，不是运行时。就像工厂开工前先检查流水线有没有接错——发现问题立刻停工，不会等到产品出了问题才发现。

---

## 3. 调度器：按课表点名

有了课表（拓扑序），调度器的工作就很简单——按顺序点名，让每个插件干活：

```python
# backend/app/factor_tick_executor.py
class FactorTickExecutor:
    def run_tick_steps(self, *, series_id: str, state: FactorTickState) -> None:
        for factor_name in self._graph.topo_order:
            plugin = self._registry.require(str(factor_name))
            plugin.run_tick(series_id=series_id, state=state, runtime=self._runtime)
```

五行代码，就是整个调度器的核心。

它做的事情：遍历拓扑序，依次调用每个插件的 `run_tick`。就像老师按花名册点名：pivot 先上台演讲，pen 第二个，zhongshu 第三个，anchor 最后。

### 插件之间怎么传递数据？

插件之间不直接对话。它们通过一个共享的"黑板"——`FactorTickState`——来传递数据：

```python
# backend/app/factor_tick_executor.py
@dataclass
class FactorTickState:
    visible_time: int                          # 当前处理到哪根蜡烛
    candles: list[Any]                         # 蜡烛数据（所有人都能看）
    events: list[FactorEventWrite]             # 产出的事件（所有人往里写）
    effective_pivots: list[PivotMajorPoint]    # pivot 写，pen 读
    confirmed_pens: list[dict]                 # pen 写，zhongshu 读
    new_confirmed_pen_payloads: list[dict]     # pen 写，zhongshu 读（本轮新增）
    zhongshu_state: dict                       # zhongshu 读写
    major_candidates: list[...]                # pivot 写，pen 读（本轮候选）
```

就像工厂的传送带：焊接工位把车架放上传送带，发动机工位从传送带上取车架、装上发动机、再放回传送带。每个工位只关心"传送带上有什么"和"我要往传送带上放什么"，不需要知道其他工位在干什么。

---

## 4. pen 的增量算法：会计的流水账

### 问题：每来一根新蜡烛，要把所有历史蜡烛重新算一遍吗？

想象你是一个会计。

老板问你："截止今天，公司总共赚了多少钱？"

**笨办法**：把公司成立以来的每一笔交易都翻出来，从头加到尾。如果公司开了 10 年，你得翻 10 年的账本。

**聪明办法**：你手边有一个"余额本"，记着截止昨天的总额。今天只需要加上今天的新交易就行了。

```text
笨办法：总额 = 第1笔 + 第2笔 + ... + 第10000笔（每天都从头算）
聪明办法：总额 = 昨天的余额 + 今天的新交易（每天只算增量）
```

pen 的算法就是"聪明办法"。它维护一个"余额本"——`effective_pivots` 列表——记录着当前有效的转折点。每来一个新的 pivot，只需要看这个列表的末尾，决定是替换还是追加。

### 核心算法：五步口诀

```python
# backend/app/factor_processor_pen.py
def append_pivot_and_confirm(self, effective, new_pivot):
    # 第①步：空本子，直接记
    if not effective:
        effective.append(new_pivot)
        return []

    last = effective[-1]

    # 第②步：同方向？留更极端的（同向替换）
    if new_pivot.direction == last.direction:
        if is_more_extreme_pivot(last, new_pivot):
            effective[-1] = new_pivot    # 新的更极端，替换
        return []                        # 同向不产生笔

    # 第③步：反方向？追加
    effective.append(new_pivot)

    # 第④步：不够3个？等着
    if len(effective) < 3:
        return []

    # 第⑤步：够3个了！确认一笔
    p0 = effective[-3]       # 起点
    p1 = effective[-2]       # 终点
    confirmer = effective[-1] # 确认者
    direction = 1 if p1.pivot_price > p0.pivot_price else -1
    return [ConfirmedPen(
        start_time=p0.pivot_time,
        end_time=p1.pivot_time,
        start_price=p0.pivot_price,
        end_price=p1.pivot_price,
        direction=direction,
        visible_time=confirmer.visible_time,  # 延迟可见！
    )]
```

口诀：**空则记，同向替，反向追，不够等，三点成。**

用一个具体例子走一遍：

```text
时间线：pivot 依次到来

① 低点 A(100) → effective = [A]           → 空则记
② 低点 B(98)  → effective = [B]           → 同向替，B 比 A 更低，替换
③ 高点 C(110) → effective = [B, C]        → 反向追
④ 高点 D(112) → effective = [B, D]        → 同向替，D 比 C 更高，替换
⑤ 低点 E(95)  → effective = [B, D, E]     → 反向追，够3个了！
                 确认笔：B→D（上涨笔）      → 三点成
⑥ 高点 F(108) → effective = [D, E, F]     → 反向追，够3个！
                 确认笔：D→E（下跌笔）      → 三点成
```

注意第⑤步：笔 B→D 的 `visible_time` 不是 D 的时间，而是 E 的时间。因为直到 E 出现（反向确认），我们才能确定 D 确实是山顶。这就是第 5 关讲的"延迟确认"——你站在山顶的时候不知道自己在山顶，得走下坡路了才知道。

### 为什么这是增量的？

关键在于 `effective_pivots` 这个列表。它就是会计的"余额本"：

- 它在每个 tick 之间**保持不变**，不会被清空
- 新 pivot 来了，只看列表末尾，做 O(1) 操作
- 不需要回溯历史，不需要重新扫描所有蜡烛

调度器在每个 tick 之间传递这个列表：

```python
# backend/app/factor_tick_executor.py
def run_incremental(self, *, series_id, process_times, effective_pivots, ...):
    for visible_time in process_times:
        tick_state = FactorTickState(
            effective_pivots=effective_pivots,  # 传入"余额本"
            confirmed_pens=confirmed_pens,
            major_candidates=[],               # 每个 tick 清空临时数据
            new_confirmed_pen_payloads=[],
            ...
        )
        self.run_tick_steps(series_id=series_id, state=tick_state)
        # tick 结束后，effective_pivots 已被 pen 插件原地更新
        # 下一个 tick 继续用更新后的列表
```

`effective_pivots` 和 `confirmed_pens` 是**跨 tick 的增量状态**，像余额本一样一直传递。而 `major_candidates` 和 `new_confirmed_pen_payloads` 是**单 tick 的临时数据**，每次清空。

---

## 5. Bootstrap：新会计怎么接手老账本

### 问题：系统重启了，"余额本"丢了怎么办？

会计辞职了，新会计来了。他没有余额本，难道要从公司成立第一天开始翻账？

不用。因为系统有**事件日志**——每一笔"确认的笔"都作为事件存进了数据库。新会计只需要：

1. 从数据库里捞出最近一段时间的事件
2. 按时间顺序重放，重建出余额本

这就是 **bootstrap**（引导恢复）：

```python
# backend/app/factor_processor_pen.py
def bootstrap_from_history(self, *, series_id, state, runtime):
    # 从历史事件中取出 pen.confirmed 事件
    raw_items = list(state.rebuild_events.get("pen") or [])
    # 规范化 payload，恢复 confirmed_pens 列表
    normalized = []
    for item in raw_items:
        if isinstance(item, dict):
            normalized.append(dict(normalize_confirmed_pen_payload(item)))
    state.confirmed_pens = normalized
```

bootstrap 也按拓扑序执行——先恢复 pivot 的状态，再恢复 pen 的状态，再恢复 zhongshu 的状态。就像新员工入职培训：先学基础（pivot），再学进阶（pen），最后学高级（zhongshu）。

---

## 6. 幂等写入：同一笔账不记两次

### 问题：如果系统崩溃后重试，会不会重复记账？

会计记了一笔"B→D 上涨笔"，系统崩了。重启后又算了一遍，又想记一笔"B→D 上涨笔"。

如果真的记了两次，账本就乱了。

解决办法：每笔事件有一个唯一的 `event_key`：

```python
# pen.confirmed 的 event_key 格式
event_key = f"confirmed:{start_time}:{end_time}:{direction}"
# 例如: "confirmed:1707000000:1707003600:1"
```

数据库有唯一约束 `(series_id, factor_name, event_key)`，重复写入时自动忽略（`ON CONFLICT DO NOTHING`）。

就像银行的转账流水号：同一笔转账，不管你提交几次，银行只会执行一次。

注意 `event_key` 里没有 `visible_time`。为什么？因为同一笔 B→D 的上涨笔，不管是在 E 出现时确认的还是在 F 出现时确认的，它都是同一笔。`visible_time` 是"什么时候发现的"，不是"这笔是什么"。身份由起止点和方向决定，不由发现时间决定。

---

## 7. pen 怎么驱动下游

pen 不是终点。它的产出会被多个下游消费：

```text
pen.confirmed
  ├→ zhongshu：消费 new_confirmed_pen_payloads，更新中枢状态
  ├→ anchor：结合 pen 强度做换锚决策
  ├→ overlay：翻译成图表上的线段
  └→ freqtrade：映射为策略信号（tc_pen_confirmed, tc_pen_dir）
```

同一笔事件，图表、策略、中枢都在消费，口径完全一致。这就是"单一事件源"的威力——不是每个消费者自己算一遍 pen，而是大家都读同一份账本。

---

## 8. 这条链背后的通用方法论

从 pen 因子链里，你能提炼出五条可以带走的工程方法论：

| 方法论 | 白话 | pen 里的体现 |
| ---- | ---- | ---- |
| 声明式依赖 | 说"我需要什么"，不说"请先做什么" | `depends_on=("pivot",)` |
| 增量推进 | 记余额，不翻旧账 | `effective_pivots` 跨 tick 传递 |
| 事件幂等 | 同一笔账不记两次 | `event_key` + UNIQUE 约束 |
| 黑板通信 | 不直接对话，通过共享状态传递 | `FactorTickState` 作为传送带 |
| fail-fast | 缺东西就停工，不偷偷降级 | 缺 `run_tick` 直接 RuntimeError |

---

## 9. 代码锚点

| 概念 | 文件 | 干什么的 |
| ---- | ---- | ---- |
| 插件契约 | `backend/app/factor_plugin_contract.py` | FactorPluginSpec 定义 |
| DAG 拓扑排序 | `backend/app/factor_graph.py` | 依赖校验 + 排序 |
| 调度器 | `backend/app/factor_tick_executor.py` | 按拓扑序执行插件 |
| pen 插件 | `backend/app/factor_processor_pen.py` | 增量算法核心 |
| pivot 插件 | `backend/app/factor_processor_pivot.py` | 依赖链起点 |
| 插件注册表 | `backend/app/factor_manifest.py` | 写侧/读侧一致性校验 |
| 增量恢复 | `backend/app/factor_rebuild_loader.py` | bootstrap 状态重建 |
| 事件存储 | `backend/app/factor_store.py` | append-only + 幂等写入 |

---

## 10. 过关自测

如果你能用自己的话回答这五个问题，第 7 关就过了：

1. 为什么插件要声明 `depends_on`，而不是手动指定执行顺序？用选课系统的比喻解释。
2. `effective_pivots` 为什么是增量算法的关键？用会计余额本的比喻解释。
3. 走一遍五步口诀：如果 effective 里有 [低A, 高B]，来了一个高C（比B更高），会发生什么？
4. `event_key` 为什么不包含 `visible_time`？用银行转账流水号的比喻解释。
5. 插件之间通过什么机制传递数据？为什么不让插件直接互相调用？
