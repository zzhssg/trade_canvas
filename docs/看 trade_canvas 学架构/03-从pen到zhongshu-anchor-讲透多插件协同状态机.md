---
title: 第3关：从 pen 到 zhongshu 与 anchor，讲透多插件协同状态机
status: done
created: 2026-02-11
updated: 2026-02-11
---

# 第3关：从 pen 到 zhongshu 与 anchor，讲透多插件协同状态机

这一关要解决一个很多人都会卡住的问题：

“我能看懂单个插件了，但一到多插件联动，就不知道状态到底是谁在改、何时改、为什么这样改。”

你如果把这一关吃透，以后看任何“策略引擎/风控引擎/推荐引擎”的协同流程都会快很多。

---

## 0. 先给结论：这套系统不是‘函数调用链’，而是‘时钟驱动的协同状态机’

每根 `closed candle` 到来，系统做一轮 tick。
这一轮里，所有插件按 DAG 拓扑顺序执行，共享同一个 `FactorTickState`，逐步推进状态。

核心顺序是：

`pivot -> pen -> zhongshu -> anchor`

你要记住：  
这不是“谁想调谁就调”，而是“按依赖图排好队，一人改一点共享状态”。

---

## 1. 为什么单看 pen 不够：pen 只负责‘笔’，不负责‘结构解释’

在第 2 关我们讲了 `pen`：它负责把 pivot 序列变成 confirmed pens。  
但交易结构里，笔只是砖，不是房子。

后面还需要两层解释：

- `zhongshu`：从笔里识别中枢结构（alive/dead、形成/死亡）。
- `anchor`：在结构演进中维护“当前锚点”（current anchor）及切换历史。

所以 pen 是“几何片段”，zhongshu/anchor 是“语义层”。

---

## 2. 多插件协同的底座：三条硬规则

### 2.1 规则一：依赖声明先行

每个插件必须在 `spec.depends_on` 声明上游：

- pen 依赖 pivot
- zhongshu 依赖 pen
- anchor 依赖 pen + zhongshu

这不是文档注释，而是调度依据。

### 2.2 规则二：拓扑顺序唯一

`FactorGraph` 校验缺依赖/环路后，产出稳定 topo order。  
执行器 `FactorTickExecutor.run_tick_steps` 严格按 topo 调插件。

意义：同输入 + 同顺序 = 同输出。

### 2.3 规则三：写侧与读侧拓扑一致

`FactorManifest` 强制 processor 与 slice plugin 的因子集合和 `depends_on` 一致。  
否则直接报错，避免写读口径漂移。

---

## 3. 这一轮 tick 里，状态是怎么接力的

`FactorTickState` 可以理解成“这一轮协同白板”，关键字段有：

- `major_candidates`（pivot 产出）
- `new_confirmed_pen_payloads`（pen 产出）
- `formed_entries`（zhongshu 产出）
- `best_strong_pen_ref / best_strong_pen_strength`（pen/anchor 共同推进）
- `anchor_current_ref / anchor_strength`（anchor 维护）

一轮接力过程：

1. **pivot** 写入 `major_candidates`。  
2. **pen** 消耗 `major_candidates`，生成 confirmed pen 事件，并写入 `new_confirmed_pen_payloads`。  
3. **zhongshu** 消耗 `new_confirmed_pen_payloads`，更新中枢状态，可能产出 `formed_entries`。  
4. **anchor** 消耗 `formed_entries` 与强笔候选，决定是否切换 anchor。  

这就是标准的“单 tick 内有向数据流”。

---

## 4. zhongshu 的双触发：既吃 pen，也吃 closed candle

`zhongshu.run_tick` 里有两个触发源：

1. 先遍历 `new_confirmed_pen_payloads`：
   - 更新中枢状态；
   - 可能产出 `zhongshu.dead` 事件；
   - 可能产生 `formed_entry`（给 anchor 用）。

2. 再基于当前 `visible_time` 的 closed candle：
   - 调 `update_state_from_closed_candle`；
   - 也可能补充 `formed_entry`。

这一步很关键：  
它说明 zhongshu 不是“只在 pen 新增时变化”，它还会随闭合蜡烛推进结构边界。

---

## 5. anchor 的双路线切换：中枢入场优先 + 强笔竞争

`anchor.run_tick` 也有两条路线：

### 路线 A：zhongshu_entry 切换

先吃 `formed_entries`，逐个尝试 `apply_zhongshu_entry_switch`。  
这是“结构性事件驱动换锚”。

### 路线 B：strong_pen 切换

再基于最后 confirmed pen + candles 构建 candidate，结合 pen 阶段筛出来的 strongest ref，走 `apply_strong_pen_switch`。  
这是“强度竞争驱动换锚”。

所以 anchor 不是拍脑袋，它是在两类证据源之间做可解释的切换决策。

---

## 6. 为什么这种协同方式比“插件互调”更稳

很多系统会让插件直接互相调用，短期快，长期乱。  
这里用了更稳的模式：**共享状态 + 拓扑调度 + 事件落盘**。

优点：

- 依赖显式：图上就能看出来。
- 调试可还原：看 tick state 即可定位责任段。
- 回放可复现：事件 append-only，状态可 bootstrap 重建。
- 演进可控：新增插件只要声明依赖，不用把全链改烂。

---

## 7. 写侧与读侧如何闭环，避免“算得对但读不出”

写侧：

- 因子插件输出事件（`pen.confirmed` / `zhongshu.dead` / `anchor.switch`）。
- 同时落 head snapshot（按 factor_name 分头）。

读侧：

- `FactorSlicesService` 按同 topo 构建快照。
- `PenSlicePlugin` / `ZhongshuSlicePlugin` / `AnchorSlicePlugin` 各自组装 history+head。

这保证了：  
同一时刻你在 API 里读到的结构，和写侧引擎推进时的结构是同一口径。

---

## 8. 给 C 语言背景读者的“脑内映射”

你可以这么类比：

- `FactorTickState` = 一个大 `struct`，每个模块只改自己字段。
- topo 调度器 = 固定执行序函数表（但顺序由依赖图算出来）。
- factor events = append-only log（像 WAL 思路）。
- bootstrap = 程序重启后从日志恢复内存态。
- manifest 校验 = 链接期契约检查，防止 ABI 不匹配。

所以你不是“从 C 跳到玄学架构”，你只是把熟悉的系统思维做了工程升级。

---

## 9. 代码锚点（按阅读顺序）

- `backend/app/factor_tick_executor.py`
- `backend/app/factor_processor_pen.py`
- `backend/app/factor_processor_zhongshu.py`
- `backend/app/factor_processor_anchor.py`
- `backend/app/factor_graph.py`
- `backend/app/factor_manifest.py`
- `backend/app/factor_rebuild_loader.py`
- `backend/app/factor_slice_plugins.py`

---

## 10. 过关自测（你应能脱稿讲清）

1. 为什么 anchor 不能在 pen 前执行？
2. `formed_entries` 是谁产出、谁消费、在同一 tick 何时可见？
3. zhongshu 为什么既看新 pen，也看当前 closed candle？
4. 为什么 manifest 要校验写侧/读侧 `depends_on` 一致？
5. 如果要新增一个依赖 zhongshu 的“风险因子”，接入最小步骤是什么？

你如果能把这五题讲顺，第 3 关就过了。
