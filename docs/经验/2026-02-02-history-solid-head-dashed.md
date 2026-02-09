---
title: "history 实线 / head 虚线 / anchor 只改颜色（防止语义漂移）"
status: done
created: 2026-02-02
updated: 2026-02-09
---

# history 实线 / head 虚线 / anchor 只改颜色（防止语义漂移）

## 问题背景

本次迭代新增了 `pen` 的分段绘制（按确认笔拆分为多段）和 `anchor` 指向笔（confirmed/candidate）并对图形做强调/染色。需要锁死展示不变量：history 必须是实线、head 必须是虚线、anchor 只能改颜色不改变实虚。

具体风险点：
1. **渲染逻辑分叉**：同一条语义（pen.confirmed）在"polyline 模式"和"分段模式"存在两套渲染路径，若不统一 `lineStyle`，容易出现风格漂移。
2. **锚染色越权**：如果 anchor 逻辑直接修改线宽/线型，会把"结构语义（history/head）"与"强调语义（anchor）"耦合。
3. **candidate 与 confirmed 混画**：若在分段模式下把 candidate 也混入 pen 段集合，会破坏"history=实线"的强语义。

## 根因

pen/anchor 的"几何数据"和"展示语义（实虚/颜色）"在代码层容易混在一起处理，缺少强制分离。

## 解法

硬约束规则：
- **history = 实线（Solid）**：`pen.history.confirmed` 及其衍生绘制必须是实线；`zhongshu.history.dead` 也应保持"稳定事实"样式。
- **head = 虚线（Dashed）**：`pen.head.candidate`、`pen.head.extending` 必须是虚线。
- **anchor 只改颜色**：anchor 只能改变颜色/透明度作为强调，不改变实虚（lineStyle 只由 pen 模块决定）。

## 为什么有效

- 把"事实 vs 候选"的语义编码为视觉不变量，可显著降低解释成本与回放对拍成本。
- anchor 不越权，避免把"强调逻辑"污染到"事实呈现"，降低后续重构风险。

## 检查清单

**开发前**
- [ ] 明确写下展示不变量：`history=实线`、`head=虚线`、`anchor 只改颜色`。
- [ ] 给每条渲染路径（polyline / segmented / replay）列出"应当使用的 lineStyle"。

**开发中**
- [ ] pen 模块负责 lineStyle（solid/dashed）；anchor 模块只能输出 ref，不直接控制 lineStyle。
- [ ] 任何 feature flag 分叉都必须共享同一套样式常量/函数（避免散落 magic numbers）。
- [ ] 新增任何结构图元时先标注它属于 history 还是 head。

**验收时**
- [ ] `cd frontend && npm run build`
- [ ] `pytest -q`
- [ ] （建议）补一条 Playwright：确保存在 candidate anchor 时，锚段是虚线；confirmed anchor 段仍是实线。

## 关联

- `frontend/src/widgets/ChartView.tsx`
- 验证命令：`cd frontend && npm run build`、`pytest -q`
