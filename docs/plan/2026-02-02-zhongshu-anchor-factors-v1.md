---
title: Zhongshu + Anchor factors v1（中枢与锚：同源、可复现、可回滚）
status: draft
owner:
created: 2026-02-02
updated: 2026-02-02
---

## 背景

当前 trade_canvas v0 已具备：
- `pivot.major`（延迟可见）→ `pen.confirmed`（延迟可见）→ `zhongshu.dead`（append-only）
- overlay 指令与 draw delta 读口的“统一形状”已经就位（`/api/draw/delta` + feature flag）

但“主干结构因子”的关键缺口仍然在：
- `zhongshu` 只有 dead，没有 `head.alive`（无法作为趋势/策略/背驰的稳定对照）
- 缺少 `anchor`（锚点选择与换锚事件流），导致后续 `divergence/趋势视图/策略门禁` 无法同源落盘

参考来源（批判性继承）：
- `../trade_system/user_data/doc/Core/factors.md`（pivot/pen/zhongshu/anchor 字段与依赖）
- `../trade_system/user_data/doc/Core/核心类 2.1.md`（锚点选择器与切片语义）

本仓真源契约：
- `docs/core/contracts/zhongshu_v1.md`
- `docs/core/contracts/anchor_v1.md`
- `docs/core/contracts/factor_v1.md`
- `docs/core/contracts/factor_graph_v1.md`
- `docs/core/contracts/draw_delta_v1.md`

## 目标 / 非目标

### 目标（Do）

1) `zhongshu`：补齐 `head.alive`（0/1 个），并保证 history/head 的冷热语义正确（无未来函数）。
2) `anchor`：落盘 append-only 的换锚事件流（history.switches），并提供 `head.current_anchor`（+ 可选 reverse_anchor）。
3) 与主链路对齐：所有输出必须以 `closed candle` 对齐点为主键，满足 `seed ≡ incremental`。
4) 可回滚：不破坏现有 `/api/overlay/delta` 与 v0 factor slices，默认行为不变（用 feature flag / 新字段兼容演进）。

### 非目标（Don’t / v1 不做）

- 不在 v1 引入完整 `divergence`、`fib`、`sr/trendline`（先把 zhongshu+anchor 的契约与真源落稳）。
- 不在已有产物时“全量重算”（终局必须增量推进；v1 允许过渡实现，但必须明确标注为 compat/projection）。
- 不把 forming 进入因子引擎。

## 方案对比（选最小闭环）

### 方案 A（推荐）：先做“切片可见”的 zhongshu.alive + anchor.switches（读时重建 head），再迁移到 hot ledger

- 写路径：仍以 append-only history 事件为真源（`zhongshu.dead`、`anchor.switch`）
- 读路径：`/api/factor/slices` 在 `at_time=t` 时用 `<=t` 的 events 重建 `zhongshu.head.alive` 与 `anchor.head.current_anchor`
- 优点：最小改动、可验收、可回滚；避免过早引入 hot ledger 复杂度
- 缺点：slice 计算成本较高（但可用 window + 缓存；后续迁移 hot ledger 不改契约）

### 方案 B：直接引入 HotLedger 并持久化 head 快照（更快但复杂）

- 优点：slice 点查快；更接近终局
- 缺点：需要先落 HotLedger 契约/表/查询；对本轮“先做调研与技术方案”跨度偏大

结论：先做方案 A；在后续 `factor-engine-graph-ledgers-v1` 的 M1 再把 head 迁入 HotLedger。

## 技术设计要点（v1 口径）

### 1) DAG 依赖

建议 v1 DAG：
- `pivot` → `pen` → `zhongshu`
- `pen + zhongshu` → `anchor`

说明：trade_system 口径为 `anchor` depends on `pen, zhongshu`；本仓可先实现 `anchor` 仅依赖 pen 的最小模式，但接口与 event schema 预留 zhongshu 解释字段。

### 2) Zhongshu（中枢）

- history：`dead[]`（append-only；`visible_time` 过滤）
- head：`alive[]`（0/1；从 `<=t` 的 confirmed pens 重建；不允许未来函数）
- v1 推荐算法：3 笔重叠形成 + 交集推进 + 交集破坏死亡（见 `docs/core/contracts/zhongshu_v1.md`）

### 3) Anchor（锚）

- **定位**：锚只作为“指向某根笔的指针（ref）”，绘图层可对被指向的笔做强调/染色。
- history：`switches[]`（append-only；**仅记录稳定切换**，推荐只记录 `kind=="confirmed"` 的换锚）
- head：`current_anchor_ref`（允许指向任意笔：confirmed 或 candidate；必须满足 `end_time<=t`）
- v1 推荐规则：保守 deterministic（强笔/中枢触发换锚），并以“确认可见时刻”作为 `switch_time`（见 `docs/core/contracts/anchor_v1.md`）

### 4) 绘图（后续里程碑）

zongshu/anchor 的绘图建议最终统一走 `draw_delta`：
- zhongshu：box/area（zg/zd 区间 + 时间范围）
- anchor：anchor_current 线段（两点 polyline）+ 可选 fib levels（后续）

本轮仅做技术方案，不要求立即实现 box 指令；可以先在侧栏/调试面板展示 slices 作为验收。

## 里程碑（每步可验收 / 可回滚）

- [ ] M0：契约落盘（本文件 + zhongshu_v1 + anchor_v1）
  - 改什么：`docs/core/contracts/zhongshu_v1.md`、`docs/core/contracts/anchor_v1.md`、本 plan
  - 怎么验收：`bash docs/scripts/doc_audit.sh`
  - 怎么回滚：`git revert`（仅文档）

- [ ] M1：后端 slices 支持 `zhongshu.head.alive`
  - 改什么：`/api/factor/slices` 的 zhongshu 输出形状补齐 head（仍保留 dead）
  - 怎么验收：pytest 新增用例（固定 fixture：formed_time<=t 时 alive 存在；death_time<=t 时 dead 出现）
  - 怎么回滚：只回滚 zhongshu head 计算/字段（history.dead 不动）

- [ ] M2：后端 factor ingest 产出 `anchor.switch`（history）+ slices 输出 `anchor.head.current_anchor`
  - 改什么：FactorOrchestrator/未来 FactorEngine 写入 anchor.switch 事件；`/api/factor/slices` 增加 anchor 快照
  - 怎么验收：pytest：同输入重跑，`switches(count,last_switch_time)` 与 `current_anchor` 一致；并验证 `end_time<=t`
  - 怎么回滚：feature flag `TRADE_CANVAS_ENABLE_ANCHOR=0`（或保留不注册 anchor 因子）

- [ ] M3：overlay/draw 绘制中枢与锚（可选，后续）
  - 改什么：overlay_orchestrator 产出 box/polyline 指令；前端 draw engine 映射渲染
  - 怎么验收：Playwright：`data-testid=chart-view` 上出现 `data-zhongshu-count>0` / `data-anchor-on=1`（或等价）
  - 怎么回滚：关闭 `VITE_ENABLE_DRAW_DELTA` 或关闭 overlay ingest 开关

## E2E 用户故事（门禁口径，规划阶段先写清）

Story ID：`2026-02-02/factor2/zhongshu-anchor-slices`

Persona：策略/结构研究者  
Goal：给定一段 `CandleClosed` 输入，在 `t` 时刻能稳定得到：
- `pen.history.confirmed` 可见
- `zhongshu.head.alive`（若已形成）与 `zhongshu.history.dead`（若已死亡）
- `anchor.head.current_anchor` 与 `anchor.history.switches`（若发生换锚）

Entry：
- `POST /api/market/ingest/candle_closed` 注入一段确定性 candles（固定 series_id）

Exit（断言）：
- `GET /api/factor/slices?series_id=...&at_time=t` 返回：
  - `snapshots["zhongshu"].meta.at_time == t`
  - `snapshots["zhongshu"].head.alive.length in {0,1}` 且 alive 的 `formed_time<=t` 且 `death_time==null`
  - 若 `dead` 非空：每项 `visible_time<=t` 且 `death_time==visible_time`
  - `snapshots["anchor"].head.current_anchor_ref.end_time<=t`（若存在）
  - `snapshots["anchor"].head.current_anchor_ref.kind in {"confirmed","candidate"}`（允许未确认锚，head-only）

Concrete Scenario（建议沿用现有 deterministic wave）：
- series_id：`binance:futures:BTC/USDT:1m`
- base=60
- 价格序列可复用 `backend/tests/test_zhongshu_dead_factor.py` 的 fixture（保证可重复）

证据命令：
- `pytest -q`（至少新增 1 条能失败的回归）
