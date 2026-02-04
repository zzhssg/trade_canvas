---
title: 复盘：pen/anchor 实线虚线语义与实现漂移风险
status: done
created: 2026-02-02
updated: 2026-02-02
---

# 复盘：pen/anchor 实线虚线语义与实现漂移风险

## 背景

本次迭代新增了：
- `pen` 的分段绘制（按确认笔拆分为多段）
- `anchor` 指向笔（confirmed/candidate）并对图形做强调/染色

同时我们想锁死一个非常重要的展示不变量：

- **history 必须是实线**
- **head 必须是虚线**
- **anchor 只能改颜色，不改变实虚**

涉及代码：`frontend/src/widgets/ChartView.tsx`。

## 具体风险点

1) **渲染逻辑分叉**：同一条语义（pen.confirmed）在“polyline 模式”和“分段模式”存在两套渲染路径，若不统一 `lineStyle`，很容易出现风格漂移（一个是实线，另一个默认为实线但未来可能改动）。
2) **锚染色越权**：如果 anchor 逻辑直接修改线宽/线型，会把“结构语义（history/head）”与“强调语义（anchor）”耦合，后续很难证明可复现与可解释。
3) **candidate 与 confirmed 混画**：若在分段模式下把 candidate 也混入 pen 段集合，会破坏“history=实线”的强语义（candidate 必须 head-only 且虚线）。

## 影响与代价

- 用户认知漂移：同一根笔在不同模式下视觉语义不一致，回放/实盘对照时难以解释。
- 回归难：缺少风格语义回归会导致 UI 变更悄悄破坏核心不变量。

## 根因

- pen/anchor 的“几何数据”和“展示语义（实虚/颜色）”在代码层容易混在一起处理。

## 如何避免（检查清单）

**开发前**
- [ ] 明确写下展示不变量：`history=实线`、`head=虚线`、`anchor 只改颜色`
- [ ] 给每条渲染路径（polyline / segmented / replay）列出“应当使用的 lineStyle”

**开发中**
- [ ] pen 模块负责 lineStyle（solid/dashed）；anchor 模块只能输出 ref，不直接控制 lineStyle
- [ ] 任何 feature flag 分叉都必须共享同一套样式常量/函数（避免散落 magic numbers）

**验收时**
- [ ] `cd frontend && npm run build`
- [ ] `pytest -q`
- [ ]（后续建议）补一条 Playwright：确保存在 candidate anchor 时，锚段是虚线；confirmed anchor 段仍是实线

## 关联与证据

- 关键文件：
  - `frontend/src/widgets/ChartView.tsx`
- 验证命令：
  - `cd frontend && npm run build`
  - `pytest -q`

