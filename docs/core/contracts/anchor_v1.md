---
title: Anchor Contract v1（锚：current + switches）
status: draft
created: 2026-02-02
updated: 2026-02-02
---

# Anchor Contract v1（锚：current + switches）

目标：为 trade_canvas 的 `anchor` 因子定义最小可落地契约，使其能：

- 基于 `pen`（以及可选 `zhongshu`）在 closed-candle 增量链路中 **动态选锚/换锚**；
- **锚本身只做“指针”**：指向某一根笔（confirmed 或 candidate），不复制笔的完整语义；
- 将“稳定的换锚”以 **append-only 的事件流**落盘（用于 replay/解释/对拍）；
- 在 `head` 暴露 t 时刻可用的 `current_anchor_ref`（以及可选 `reverse_anchor_ref`）供策略/背驰/趋势视图消费；
- 满足 `seed ≡ incremental`，避免“末态倒推历史”。

依赖（DAG）：
- `pen`（必需）
- `zhongshu`（v1 可选，但推荐纳入：trade_system 口径为 `anchor` depends on `pen, zhongshu`）

关联契约：
- 因子外壳与冷热语义：`docs/core/contracts/factor_v1.md`
- Zhongshu 结构：`docs/core/contracts/zhongshu_v1.md`

---

## 1) 数据结构

### 1.1 PenRef（锚指针：指向一根笔）

锚点本质上是“指向一根笔的引用”；绘制/策略若需要笔的几何信息，应从 `pen` 的 `history/head` 中按 ref 解析得到。

```ts
type PenRefV1 = {
  // 指向的笔类型：
  // - confirmed：已确认结构笔（history）
  // - candidate：候选笔/末笔（head，可重绘）
  kind: "confirmed" | "candidate"

  // 用于定位的最小字段：时间边界 + 方向
  start_time: number
  end_time: number
  direction: number // +1 up, -1 down
}
```

约束：
- `end_time <= at_time`（head/current_anchor_ref 的可见性门禁）
- `kind=="candidate"` 时，`end_time` 通常等于 `at_time`（表示“以 t 为止的候选末笔”）；允许随着 t 推进重绘。
- `kind=="confirmed"` 时，该 ref 必须能在 `pen.history.confirmed`（或等价字段）中唯一匹配。

### 1.2 AnchorSwitch（稳定换锚事件，history）

```ts
type AnchorSwitchV1 = {
  switch_time: number         // 事件对外可见时刻（unix seconds；<= at_time 才能出现在 history）
  reason: string              // "strong_pen" | "zhongshu_first_pen" | "manual" | ...

  old_anchor?: PenRefV1 | null
  new_anchor: PenRefV1

  // 可选：用于解释/调试（不进入策略硬依赖）
  related_zhongshu?: {
    formed_time: number
    zg: number
    zd: number
  } | null
}
```

硬约束：
- append-only：同一个 `switch_time + new_anchor` 的换锚必须幂等去重（event_key 稳定）。
- `switch_time` 必须是一个“已确认可见”的时刻（不允许未来函数）。
- **稳定性门禁**：写入 `history.switches` 的换锚必须是“稳定的”（推荐仅记录 `kind=="confirmed"` 的切换）；`candidate` 级别的快速摆动应留在 head，不落 history（否则会引入高频噪声与不可解释的 append-only 膨胀）。

### 1.3 Slice 形状（外壳）

```ts
type AnchorSliceV1 = FactorSliceV1 & {
  history: {
    switches: AnchorSwitchV1[]     // append-only（switch_time<=t）
  }
  head: {
    current_anchor_ref: PenRefV1 | null
    reverse_anchor_ref?: PenRefV1 | null
  }
}
```

---

## 2) 语义与不变量（硬门禁）

1) **依赖只能来自 deps_snapshot**：切片/计算阶段读取 `pen/zhongshu` 必须来自 `deps_snapshot`，禁止回调依赖因子的 `slice_at()`。
2) **history 纯切片**：`history.switches` 只能按 `switch_time<=t` 过滤，禁止重算。
3) **head 无未来函数**：
   - `head.current_anchor_ref` 必须满足 `end_time<=t`；
   - 若候选锚的确认需要上游事件（例如新 pen.confirmed 出现），则 `switch_time` 必须取“确认可见”时刻，而不是结构发生的更早时刻。
4) **seed ≡ incremental**：同一段输入在新 DB 重跑，固定 `t` 下：
   - `switches` 的 `(count,last_switch_time)` 一致；
   - `current_anchor_ref` 的 `(kind,start_time,end_time,direction)` 一致。

---

## 3) v1 推荐实现口径（确定性优先）

v1 的目标不是“最强语义”，而是“可复现 + 可验收 + 可演进”。建议先落一个确定性、保守的规则集，并版本化迭代：

### 3.1 初始锚选择（两种来源，择一或按优先级）

- `strong_pen`：在可见的 confirmed pens 中选择“力度最大”的一根作为初始锚（力度口径必须唯一：例如 `abs(end_price-start_price)`；更复杂口径后续版本化）。
- `zhongshu_first_pen`：当首次形成 `zhongshu.head.alive` 时，选择该中枢形成窗口内的“第一根结构笔”作为锚（需要 zhongshu 提供可定位的 formed_time/start_time）。

### 3.2 换锚规则（保守）

只在“确定可见的新证据”到来时换锚：

- 当出现一根新的 confirmed pen，且其力度明显超过当前锚（阈值可参数化），产生 `AnchorSwitchV1`；
- 或当检测到“新中枢形成”并满足策略口径时触发（可选）。

可见性：
- `switch_time` 推荐直接使用触发该切换的 confirmed pen 的 `visible_time`（或等价确认时刻），避免未来函数。

---

## 4) 绘图与“染色”（非本因子职责，但需要对齐口径）

锚允许指向未确认笔（candidate），其价值在于“第一时间捕捉趋势变化”。但“如何画出来/如何染色”应归属于绘图层（draw delta / overlay 指令）：

- `anchor` 因子只输出 `*_anchor_ref`（指针），不输出颜色/线宽等 style。
- 绘图层可以用两种方式表现锚：
  1) 生成一条单独的 overlay 指令（例如 `anchor.current` 的 polyline/segment），用不同颜色强调；
  2) 或在前端 apply 时，根据 `anchor.current_anchor_ref` 去 pen 的几何数据中定位对应段并染色（需要 pen 绘制不是“单条 polyline 全同色”，而是可分段样式）。

约束：无论哪种方式，绘图必须使用 `<=t` 的数据，且不得让“候选锚”的展示反向污染 `pen.history.confirmed` 的真源语义。
