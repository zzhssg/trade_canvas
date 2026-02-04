---
title: 经验：history 用实线、head 用虚线（anchor 只改颜色）
status: done
created: 2026-02-02
updated: 2026-02-02
---

# 经验：history 用实线、head 用虚线（anchor 只改颜色）

## 场景与目标

结构因子（pen/zhongshu/anchor）在 trade_canvas 里既要“可复现真源”（history）又要“及时感知趋势变化”（head）。
如果没有稳定的展示语义约束，回放/实盘/解释会出现认知漂移。

目标：
- 用户一眼区分：哪个是稳定事实（history），哪个是可重绘候选（head）
- anchor 强调趋势时不篡改事实语义，仅做视觉强调

## 可复用规则（硬约束）

- **history = 实线（Solid）**
  - `pen.history.confirmed` 及其衍生绘制必须是实线
  - `zhongshu.history.dead`（后续 box/area）也应保持“稳定事实”样式（不闪烁、不重绘）
- **head = 虚线（Dashed）**
  - `pen.head.candidate`、`pen.head.extending`（若实现）必须是虚线
  - `anchor.head.*_ref.kind=="candidate"` 对应的高亮也必须是虚线
- **anchor 只改颜色**
  - anchor 只能改变颜色/透明度作为强调，不改变实虚（lineStyle 只由 pen 模块决定）

## 为什么有效

- 把“事实 vs 候选”的语义编码为视觉不变量，可显著降低解释成本与回放对拍成本。
- anchor 不越权，避免把“强调逻辑”污染到“事实呈现”，降低后续重构风险。

## 复用方式（检查清单）

- [ ] 新增任何结构图元时先标注它属于 history 还是 head
- [ ] UI 只允许 pen 模块决定 lineStyle；anchor 只能提供 ref + color token
- [ ] 有 feature flag 分叉（polyline/segmented）时，确保两条路径共享同一套 lineStyle 规则

## 关联与证据

- 关键文件：`frontend/src/widgets/ChartView.tsx`
- 验证命令：
  - `cd frontend && npm run build`
  - `pytest -q`

