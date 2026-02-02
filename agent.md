# trade_canvas 开发协作说明（agent）

目标：从零重构一套“因子引擎 + 图表 + freqtrade 实盘接入”的干净架构，保持小步迭代、可验收、可回滚。

## 批判性继承：参考 trade_system（但不复刻屎山）
`trade_system` 是被废弃的老项目（代码层面不再追随），但其 `user_data/doc/Core` 有不少“可直接指导实现”的好设计，可以作为参考来源。

使用原则：
- 继承“契约/术语/不变量”，不继承“实现细节/工程负债”。
- 任何继承都要在本仓重新落盘（更短、更可测试），并配套最小 E2E 验收。

建议优先阅读：
- `../trade_system/user_data/doc/Core/核心类 2.1.md`
- `../trade_system/user_data/doc/Core/术语与坐标系（idx-time-offset）.md`
- `../trade_system/user_data/doc/Core/ARCHITECTURE.md`
- `../trade_system/user_data/doc/Core/Contracts/factor_ledger_v1.md`
- `../trade_system/user_data/doc/Core/Contracts/slot_delta_ledger_v1.md`
- `../trade_system/user_data/doc/Core/【SAD】Replay 协议总览（Package-Explain-QueryView）.md`

继承落地流程（每次只做一小步）：
1) 选一个 doc 结论（≤3 条）→ 写成 trade_canvas 的短契约（schema/接口/不变量）。
2) 实现最小闭环（mock 输入也行）→ 加一条“能失败的”验收（例如不同步时拒绝交易）。
3) 反向对拍：同一份输入重复运行，输出可复现（同输入同输出）。

## 一句话架构
- `closed candle` 是权威输入：驱动因子计算、指标展示（ledger+overlay）。
- `forming` 只用于蜡烛展示（不进因子引擎、不落库、不影响策略信号）。
- 策略与图表同源：同一根 `candle_id` 的一次 `apply_closed()` 同时产出 `ledger`（策略）与 `overlay`（绘图指令）。

## 术语与约束（必须一致）
- `candle_id`：`{symbol}:{timeframe}:{open_time}`（或等价确定性标识），所有下游对齐都用它。
- `history`：冷数据，append-only，只接受 `CandleClosed`。
- `head`：热数据，可重绘，仅用于 forming 蜡烛展示（首期可不做）。
- 禁止：在已有产物时全量重算；必须基于已有状态做增量更新（无产物才允许全量重建）。

## MVP（用户故事驱动验收）
首期只做一个端到端闭环用户故事（先 dry-run，不真下单）：
1) 系统接收一段 `CandleClosed` 序列（先用回放/mock）。
2) 因子引擎逐根增量计算，落库 event log，并产出 `ledger + overlay`。
3) 前端图表能展示蜡烛 + overlay（先 mock overlay 也可）。
4) `freqtrade` 策略通过 adapter 读取 `latest_ledger` 并产生 dry-run 信号。
5) 若 `candle_id` 不一致，策略必须拒绝出信号（fail-safe）。

## 目录建议（逐步落地，不一次性全建）
- `frontend/`：图表与操作台（Vite/React/TS/Tailwind）。
- `packages/factor_kernel/`：因子内核（只吃 closed）。
- `packages/factor_store/`：event log + snapshot（可先 sqlite/jsonl）。
- `packages/adapters/`：
  - `freqtrade_adapter/`：ledger → dataframe/信号
  - `chart_adapter/`：overlay → 前端（ws/http）
- `fixtures/`：黄金数据（固定 K 线样本，用于可复现测试）

## 运行与检查
前端：
- `cd frontend && npm install && npm run dev`
- `cd frontend && npm run build`

Python / freqtrade：
- `source .env/bin/activate`
- `freqtrade --version`

## 前端入口（快速定位）
- AppShell：`frontend/src/layout/AppShell.tsx`
- Sidebar：`frontend/src/parts/Sidebar.tsx`
- TopBar：`frontend/src/parts/TopBar.tsx`
- BottomTabs：`frontend/src/parts/BottomTabs.tsx`
- Chart：`frontend/src/widgets/ChartView.tsx`

