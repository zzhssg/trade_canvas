---
title: 第5关：从肉眼看图到算法看图——缠论的 pivot/pen/zhongshu
status: done
created: 2026-02-11
updated: 2026-02-11
---

# 第5关：从肉眼看图到算法看图——缠论的 pivot/pen/zhongshu

上一关你学会了 K 线——量化交易的"原始语言"。

但光看 K 线，就像光看体温计的数字——36.5、37.2、38.1、37.8——你知道数字在变，但看不出"这个人是在发烧还是在退烧"。

你需要一套方法，从一堆跳动的数字里**提炼出趋势和结构**。

这个系统用的方法叫"缠论"——一种中国本土的技术分析理论。别被名字吓到，它的核心逻辑其实很朴素。这一关我们用最白的话把它讲透。

---

## 1. 先看一座山：什么是"趋势"

想象你站在一片山脉前面。

你的眼睛会自动做三件事：
1. 找到山顶和山谷（**转折点**）
2. 把相邻的山顶和山谷连成线（**趋势段**）
3. 发现某些地方山路反复上下（**震荡区**）

缠论做的事情一模一样，只不过把"山脉"换成了"K 线图"：

```text
价格
 ^
 |    ⛰️B
 |   / \        ⛰️D
 |  /   \      / \
 | /     \    /   \
 |/    ⛰️C \  /     \
 |A         \/       \E
 +------------------------→ 时间

人眼看到：A 到 B 涨了，B 到 C 跌了，C 到 D 又涨了……
算法看到：pivot=[A,B,C,D,E], pen=[AB,BC,CD,DE]
```

缠论把这个过程分成三层，每一层都是上一层的"提炼"：

| 层 | 名字 | 白话 | 比喻 |
| ---- | ---- | ---- | ---- |
| 第一层 | Pivot（枢纽点） | 找出价格的高低转折点 | 找山顶和山谷 |
| 第二层 | Pen（笔） | 把相邻转折点连成线段 | 画山脊线 |
| 第三层 | Zhongshu（中枢） | 找出几笔重叠的震荡区域 | 圈出山间盆地 |

下面一层一层讲。

---

## 2. 第一层：Pivot——找山顶和山谷

### 问题：怎么判断一个点是"山顶"？

你站在一个点上，往左看、往右看，如果两边都比你矮，你就是山顶。

翻译成算法：一根 K 线的最高价，如果比左边 N 根和右边 N 根的最高价都高，它就是一个"高点枢纽"（resistance pivot）。

这个 N 就是"窗口"（window）。窗口越大，要求越严格，找出来的山顶越"重要"。

```python
# backend/app/factor_processor_pivot.py
# 检查一个点是不是"山顶"（高点枢纽）
target_high = float(candles[idx].high)

# 左边 window 根都比我矮吗？（严格小于）
is_max_left = all(float(candles[i].high) < target_high
                   for i in range(idx - w, idx))

# 右边 window 根都不比我高吗？（允许相等）
is_max_right = all(float(candles[i].high) <= target_high
                    for i in range(idx + 1, idx + w + 1))
```

注意一个细节：左边要求**严格小于**（`<`），右边允许**相等**（`<=`）。为什么？

因为如果左右都要求严格小于，那两根一样高的蜡烛就谁都不是山顶了。右边放宽到"不比我高"，就能在平顶的情况下选出一个确定的山顶。

### Major vs Minor：大山和小丘

系统找两种枢纽点：

- **Major（主枢纽）**：用标准窗口（比如 5）。找出来的是"大山"——重要的转折点。
- **Minor（次枢纽）**：在两个 major 之间，用更大的窗口（2 倍）找"小丘"——次要的转折点。

就像看地图：major 是省会城市，minor 是地级市。先标省会，再在省会之间标地级市。

### 为什么需要"等右边确认"

一个关键设计：pivot 不是在"山顶那一刻"被发现的，而是在"右边 N 根蜡烛都出来之后"才被确认的。

就像你爬山，站在山顶的时候你不知道自己在山顶——你得继续往前走，发现路开始往下了，回头看才知道"刚才那个点是山顶"。

这就是为什么 pivot 有两个时间：`pivot_time`（山顶的时间）和 `visible_time`（确认的时间）。

---

## 3. 第二层：Pen——把山顶和山谷连成线

### 问题：有了转折点，怎么画趋势线？

找到了一堆山顶和山谷，下一步是把它们连成线段。每一段就是一"笔"（Pen）。

一笔 = 从一个转折点到下一个**反方向**的转折点。

```text
价格
 ^
 |    B(高)
 |   /|\
 |  / | \      D(高)
 | /  |  \    /|
 |/   |   \  / |
 A(低)|    \/  |
      |    C(低)|
      |         |
  笔1: A→B(上涨)
  笔2: B→C(下跌)
  笔3: C→D(上涨)
```

### 两条铁规则

笔的确认有两条规则，非常精炼：

**规则一：同向替换**

如果新来的枢纽点和上一个方向相同（都是高点或都是低点），保留更极端的那个。

就像跳高比赛：两个选手都跳了 2 米，保留跳得更高的那个。

```python
# backend/app/factor_processor_pen.py
if new_pivot.direction == last.direction:
    # 同方向？保留更极端的
    if is_more_extreme_pivot(last, new_pivot):
        effective[-1] = new_pivot  # 替换
    return []  # 不产生新笔
```

**规则二：反向追加，三点成笔**

如果新来的枢纽点方向相反（上一个是高点，这个是低点），追加进去。当积累了 3 个点（低-高-低 或 高-低-高），就确认一笔。

为什么要 3 个点？因为 2 个点只能画一条线，你不知道趋势有没有结束。第 3 个点是"确认者"——它证明了趋势确实反转了。

```python
# backend/app/factor_processor_pen.py
effective.append(new_pivot)       # 反向，追加
if len(effective) < 3:
    return []                     # 不够3个点，等着

p0 = effective[-3]                # 起点
p1 = effective[-2]                # 终点
confirmer = effective[-1]         # 确认者
direction = 1 if p1.pivot_price > p0.pivot_price else -1
# 确认一笔：从 p0 到 p1，方向由价格决定
```

就像法庭判案：原告说"他偷了我的钱"（第 1 个点），被告说"我没偷"（第 2 个点），证人出来作证（第 3 个点）——有了证人，法官才能下判决。

---

## 4. 第三层：Zhongshu——找出山间盆地

### 问题：怎么知道价格在"震荡"？

有了笔之后，你会发现有些地方，价格上去一点、下来一点、又上去一点——在一个区间里反复横跳。

这个区间就是"中枢"（Zhongshu）。

```text
价格
 ^
 |         ╔═══════════╗
 |    /\   ║  中枢区间  ║  /\
 |   /  \  ║ (zg=上界) ║ /  \
 |  /    \ ║           ║/    \
 | /      \║ (zd=下界) ║      \
 |/        ╚═══════════╝
 +--------------------------------→ 时间
```

中枢的定义：**至少三笔的价格区间有重叠**。

具体来说，系统会看连续几笔的高低点范围，如果它们有交集，交集区域就是中枢。

- `zg`（中枢上界）：重叠区域的上边界
- `zd`（中枢下界）：重叠区域的下边界

```python
# backend/app/zhongshu.py
@dataclass(frozen=True)
class ZhongshuAlive:
    start_time: int          # 中枢开始时间
    end_time: int            # 中枢结束时间
    zg: float                # 上界（天花板）
    zd: float                # 下界（地板）
    entry_direction: int     # 进入方向：1=上涨进入，-1=下跌进入
```

### Alive vs Dead：活中枢和死中枢

中枢有两种状态：

- **Alive（活的）**：价格还在中枢区间里震荡，中枢还在"生长"。
- **Dead（死的）**：价格突破了中枢的上界或下界，中枢"结束"了。

```python
# backend/app/zhongshu.py
@dataclass(frozen=True)
class ZhongshuDead:
    zg: float                # 上界
    zd: float                # 下界
    death_time: int          # 死亡时间（被突破的时间）
```

就像一个湖泊：水位在湖岸之间涨涨落落（alive），直到有一天洪水冲破了堤坝（dead）——湖泊消失了，水流向了新的方向。

### 中枢的意义：震荡区是"战场"

为什么要找中枢？因为中枢是多空双方的"战场"。

- 价格在中枢里震荡 = 买方和卖方势均力敌，谁也打不过谁。
- 价格向上突破中枢 = 买方胜出，可能开始上涨趋势。
- 价格向下突破中枢 = 卖方胜出，可能开始下跌趋势。

这就是量化交易的核心逻辑之一：**在中枢突破的时候下注**。

---

## 5. 三层怎么串起来：流水线调度

这三层不是各自独立运行的，而是像流水线一样串联：

```text
每来一根 closed 蜡烛：
  ① Pivot 先算 → 找到新的转折点了吗？
  ② Pen 再算   → 新转折点能确认一笔吗？
  ③ Zhongshu 最后算 → 新笔影响中枢了吗？
```

调度器按 DAG 拓扑顺序依次调用：

```python
# backend/app/factor_tick_executor.py
class FactorTickExecutor:
    def run_tick_steps(self, *, series_id: str, state: FactorTickState) -> None:
        for factor_name in self._graph.topo_order:
            # topo_order = ("pivot", "pen", "zhongshu", "anchor")
            plugin = self._registry.get(factor_name)
            plugin.run_tick(series_id=series_id, state=state, runtime=self._runtime)
```

每个插件算完后，结果会写进共享的 `FactorTickState`，下一个插件可以直接读取：

```python
# backend/app/factor_tick_executor.py
@dataclass
class FactorTickState:
    visible_time: int                          # 当前处理到哪根蜡烛
    candles: list[Any]                         # 蜡烛数据
    events: list[FactorEventWrite]             # 产出的事件（所有插件共享）
    effective_pivots: list[PivotMajorPoint]    # pivot 的产出 → pen 的输入
    confirmed_pens: list[dict]                 # pen 的产出 → zhongshu 的输入
    zhongshu_state: dict                       # zhongshu 的状态
    new_confirmed_pen_payloads: list[dict]     # 本轮新确认的笔
```

就像接力赛：第一棒（pivot）跑完把接力棒（effective_pivots）交给第二棒（pen），第二棒跑完把接力棒（confirmed_pens）交给第三棒（zhongshu）。

---

## 6. 一个完整的例子

假设 BTC 价格这样变化（1 分钟线）：

```text
时间:  T1    T2    T3    T4    T5    T6    T7    T8    T9    T10
价格: 100 → 102 → 105 → 103 → 101 → 99 → 102 → 104 → 101 → 103
```

**Pivot 看到的**：
- T3（105）是高点：左边 T1、T2 都比它低，右边 T4、T5 也比它低 → 确认为 resistance pivot
- T6（99）是低点：左边 T4、T5 都比它高，右边 T7、T8 也比它高 → 确认为 support pivot

**Pen 看到的**：
- 有了 T3（高）和 T6（低），但只有 2 个点，不够
- 等 T8（104）被确认为高点 → 3 个点了：T3(高)-T6(低)-T8(高)
- 确认笔：T3→T6（下跌笔），T6→T8 等待下一个低点确认

**Zhongshu 看到的**：
- 等积累了至少 3 笔，检查它们的价格区间有没有重叠
- 如果有 → 形成中枢，标记 zg 和 zd
- 如果价格突破 → 中枢死亡，趋势开始

---

## 7. 为什么要用算法而不是肉眼

你可能觉得："这些我用眼睛看不就行了？"

不行。原因有三：

**一、人眼会骗你。** 你看到连续 5 根绿色蜡烛，本能觉得"要涨了"。但算法会告诉你：pivot 还没确认，别急。

**二、人眼不够快。** 你盯着一个交易对还行，同时盯 50 个交易对、6 个时间框架？算法可以。

**三、人眼不可复现。** 你今天看图觉得"这里是中枢"，明天再看可能觉得"好像不是"。算法每次看到同样的数据，给出同样的结论。

这就是第 1 关讲的铁律：**closed 才算数，同输入同输出。** 算法保证了可复现性。

---

## 8. 代码锚点

| 概念 | 文件 | 干什么的 |
| ---- | ---- | ---- |
| Pivot 计算 | `backend/app/factor_processor_pivot.py` | 找高低转折点 |
| Pen 计算 | `backend/app/factor_processor_pen.py` | 连转折点成笔 |
| Zhongshu 计算 | `backend/app/factor_processor_zhongshu.py` | 找震荡中枢 |
| Zhongshu 核心算法 | `backend/app/zhongshu.py` | 中枢状态机 |
| 流水线调度 | `backend/app/factor_tick_executor.py` | 按 DAG 顺序调用插件 |
| 共享状态 | `backend/app/factor_tick_executor.py` | FactorTickState 定义 |
| 插件契约 | `backend/app/factor_plugin_contract.py` | FactorTickPlugin 接口 |

---

## 9. 过关自测

如果你能用自己的话回答这五个问题，第 5 关就过了：

1. Pivot 怎么判断一个点是"山顶"？为什么需要左右各 N 根蜡烛来确认？
2. Pen 的"同向替换、反向追加"是什么意思？用跳高比赛和法庭判案的比喻解释。
3. 为什么确认一笔需要 3 个点而不是 2 个点？
4. Zhongshu 的 zg 和 zd 分别代表什么？"alive"和"dead"的区别是什么？
5. 三层因子的计算顺序是什么？为什么不能乱序？用接力赛的比喻解释。
