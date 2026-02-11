---
title: Zhongshu Contract v1（中枢：dead + alive）
status: done
created: 2026-02-02
updated: 2026-02-11
---

# Zhongshu Contract v1（中枢：dead + alive）

目标：为 trade_canvas 的 `zhongshu` 因子定义最小可落地契约，使其能：

- 从 `pen` 的已确认结构（history）**无未来函数**派生中枢结构；
- 以 **append-only 的 dead 事件流**表达已死亡中枢；
- 以 **head.alive**表达 t 时刻的“当前活中枢”（0/1 个，允许重绘但不得未来函数）；
- 支持 replay/live 同口径（`seed ≡ incremental`）。

依赖：
- `pen`（上游；必须从 `deps_snapshot["pen"]` 读取，不得回调 `pen.slice_at()`）
- 因子外壳与冷热语义：`docs/core/contracts/factor_v1.md`

---

## 1) 数据结构

### 1.1 Zhongshu（结构体）

```ts
type ZhongshuV1 = {
  // 中枢覆盖的结构边界（时间）
  start_time: number
  end_time: number

  // 中枢区间（价格）
  zg: number  // upper bound（最高可接受上边界）
  zd: number  // lower bound（最低可接受下边界）

  // 生命周期关键时刻（均为 unix seconds，且必须 <= 可见时刻）
  formed_time: number
  formed_reason?: "pen_confirmed" | "price_cross"
  death_time?: number | null   // 仅 dead 中枢有；alive 为 null

  // 可见时刻（用于 history 切片过滤）
  visible_time: number
}
```

约束：
- `zd <= zg`，否则结构无效，必须丢弃/拒绝落盘。
- `formed_time` 必须满足 `start_time <= formed_time <= visible_time`。
- dead 中枢必须满足：`death_time != null` 且 `death_time == visible_time`（死亡在“确认可见”那根笔/那根收线时刻对外可见）。

说明：
- `formed_reason="pen_confirmed"`：按传统 4 笔确认时刻形成（P3 确认可见）。
- `formed_reason="price_cross"`：在 P3 延伸期间，closed K 的 high/low 首次越过 `P1.end_price` 提前确认。

### 1.2 Slice 形状（外壳）

```ts
type ZhongshuSliceV1 = FactorSliceV1 & {
  history: { dead: ZhongshuV1[] }        // append-only（visible_time<=t）
  head: { alive: ZhongshuV1[] }          // 0/1 个（formed_time<=t；death_time==null）
}
```

---

## 2) 语义与不变量（硬门禁）

1) **只吃 closed-candle + confirmed 语义输入**：
   - 结构候选与区间计算只能基于 `pen.history.confirmed`（或等价字段）；
   - 允许用 `closed candle`（仅 `high/low`）触发 `price_cross` 提前确认；
   - 严禁使用 forming/extending/tick 数据（避免未来函数）。
2) **history 纯切片**：`zhongshu.history.dead` 必须仅按 `visible_time<=t` 过滤；禁止在 slice 阶段重算 dead 列表。
3) **head 无未来函数**：`head.alive(t)` 允许用 `<=t` 的 confirmed pens + closed candles 进行短窗重算，但不得读取 `>t` 的任何数据；若存在 hot ledger，应优先读 hot 的点查快照。
4) **seed ≡ incremental**：同一段 `CandleClosed[]` 输入，在新 DB 上重跑：
   - `dead` 的 `(count,last_visible_time,last_zg/zd)` 必须一致
   - `alive` 在同一 `t` 的结果必须一致（至少 `(formed_time, zg, zd)` 一致）

---

## 3) 最小算法口径（v1 推荐，确定性且保守）

v1 使用“前向生长”的 4 笔语义（进入笔 + 构成三笔），并支持“提前确认”：

- **形成窗口**：从最早可见 confirmed pen 开始，按时间前向扫描任意连续 4 笔 `P1,P2,P3,P4`。
  - `P1` 是进入笔；
  - `P2,P3,P4` 是构成段。
- **形成条件**：`P1~P4` 这 4 笔必须存在公共重叠区间（即四笔交集非空），否则该 4 笔窗口不形成中枢，继续向前滑动窗口。
- **中枢区间计算**：一旦形成，`zg/zd` 只由 `P2,P3,P4` 决定：
  - `zg = min(high(P2), high(P3), high(P4))`（高点中取最低）
  - `zd = max(low(P2), low(P3), low(P4))`（低点中取最高）
- **确认时刻（formed_time）**：取以下两种触发里“更早且可见”的时刻：
  1) `price_cross`：第三构成段（P3）延伸期间，closed K 的 high/low 首次越过 `P1.end_price`；
  2) `pen_confirmed`：P3 成为 confirmed pen 的可见时刻（原口径兜底）。
- **price_cross 默认判定**：
  - 若 `P3` 为下行段：首次满足 `closed.low <= P1.end_price`；
  - 若 `P3` 为上行段：首次满足 `closed.high >= P1.end_price`。
- **存活推进**：中枢形成后 `zg/zd` 固定不变；后续笔仅推进 `end_time`，不允许“越走越窄”。
- **死亡条件**（同侧脱离）：任意后续笔若整体落在中枢上方或下方即死亡：
  - `pen_high < zd`（整笔在下方）或 `pen_low > zg`（整笔在上方）。
  - 该笔对应 `death_time=visible_time=current_pen.visible_time`。
- **死亡后重置起点（reseed）**：死亡事件发生后，把“死亡前一笔”记为 `p0`，把“导致死亡的笔”记为 `p1`。后续新中枢构建时：
  - 只允许使用 `start_time >= p0.start_time` 的笔参与扫描；
  - 不允许回退使用 `p0` 之前的笔作为进入笔（防止语义回看）；
  - 若从 `p0` 起的第一组窗口未满足“进入笔 + 后续三笔重叠”，则继续向后滑动，直到首次满足再确认。
- **下一中枢**：在 reseed 约束下继续沿时间向前扫描，按同一规则寻找下一个“进入笔 + 三笔构成段”。

说明：
- 该口径满足“从前往后生长”，并保持 replay/live 一致（仅依赖 confirmed pens 的 `visible_time` 顺序）。
- 后续若要升级为更丰富的中枢语义（多级别/多段），应以版本化方式扩展（`schema_version` 升级或新增字段），不要静默改口径。
