---
title: Strategy Contract v1（策略类数据结构）
status: draft
created: 2026-02-02
updated: 2026-02-02
---

# Strategy Contract v1（策略类数据结构）

目标：定义 trade_canvas 的策略类在“因子引擎/实盘适配（freqtrade）/回放/解释/绘图”之间的最小数据结构边界。

本契约“批判性继承”自 `trade_system` 的关键口径：
- 策略只负责“业务决策/信号”，不把装配细节散落在各处（装配应可集中、可哈希、可复现）。
- 策略消费同源快照（`FactorSliceV1` / ledger 视角），禁止直接重算因子。
- 策略输出应可解释（能指回使用了哪些因子字段/事件），并且对齐 `at_time`。

关联真源：
- 因子外壳：`docs/core/contracts/factor_v1.md`
- K 线坐标与主键：`docs/core/market-kline-sync.md`

---

## 1. 策略静态描述（结构，而非实现）

```ts
type StrategySpecV1 = {
  strategy_name: string
  strategy_version: string  // 手工版本号或 git sha（必须稳定）

  // 能力声明
  can_long: boolean
  can_short: boolean

  // 该策略要使用的因子根（系统应按依赖闭包补齐）
  factor_roots: string[]

  // 参数（影响因子与信号；进入缓存 key）
  params_schema: Record<string, any>

  // 可复现性：装配与逻辑的 hash（策略/插件组合变化即变化）
  logic_hash: string
}
```

约束：
- `strategy_name` 为稳定 key；`strategy_version` 用于演进与回溯（避免“同名不同义”）。
- `factor_roots` 只描述“我需要哪些快照”，不描述“如何计算”（计算由因子引擎负责）。

---

## 2. 策略运行时输入（决策所需最小闭包）

其中 `FactorSliceV1` 的定义见：`docs/core/contracts/factor_v1.md`。

```ts
type StrategyInputV1 = {
  series_id: string
  epoch: number
  at_time: number
  candle_id: string

  // 策略可选择同时读取一小段 candle window（用于价格/波动度等直接特征）
  candles?: Array<{
    candle_time: number
    open: number
    high: number
    low: number
    close: number
    volume: number
  }>

  // 因子快照（应由 slice_selected 构造“最小依赖闭包”）
  snapshots: Record<string, FactorSliceV1>

  // 可选：账户/持仓快照（由实盘 adapter 注入）
  portfolio?: {
    position_size?: number
    avg_entry_price?: number
    unrealized_pnl?: number
  }
}
```

约束：
- 策略不得依赖 `>at_time` 的信息（无未来函数）。
- `snapshots[*].meta.at_time` 必须全部等于 `at_time`（否则必须 fail-safe：拒绝出信号）。

---

## 3. 策略输出（信号 + 解释）

```ts
type StrategySignalV1 = {
  kind: "entry" | "exit" | "adjust"
  side: "long" | "short"
  strength?: number        // 0..1（可选）

  // 风控建议（可选；由 adapter 决定如何映射到具体交易系统）
  stop_loss_price?: number
  take_profit_price?: number

  // 可解释性：指回快照字段（不强制标准化到细粒度，但至少能定位到 factor）
  reasons?: Array<{
    factor_name: string
    path?: string           // 例如 "history.confirmed_pens[-1]"（仅用于诊断）
    note?: string
  }>
}

type StrategyOutputV1 = {
  schema_version: 1
  series_id: string
  epoch: number
  at_time: number
  candle_id: string
  strategy_name: string
  strategy_version: string
  signals: StrategySignalV1[]
}
```

建议：
- `signals=[]` 表示“无动作”，而不是 `null`（便于 append-only 记录）。
- 输出应保持 JSON 友好，以便落库（event log）、回放、解释与前端展示。

---

## 4. 策略与因子引擎的边界（必须清晰）

策略层应该：
- 声明所需 `factor_roots`（以及策略 params）；
- 消费 `snapshots` 生成 `signals`；
- 在快照不一致/缺失时 fail-safe（拒绝输出信号）。

策略层不应该：
- 直接重算任何因子（否则 replay/live/overlay 必漂移）。
- 依赖 idx 作为跨窗口对齐主键（idx 只能是窗口内派生信息）。
