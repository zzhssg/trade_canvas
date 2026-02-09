---
title: "锚顶层渲染（解决 pen 遮挡导致锚不可见）"
status: done
created: 2026-02-09
updated: 2026-02-09
---

# 锚顶层渲染（解决 pen 遮挡导致锚不可见）

## 问题背景

锚切换语义修复后，用户反馈"4h 图仍看不到锚绘图"。`data-anchor-count > 0` 说明锚指令已到前端，但主图上视觉不稳定，锚线会被笔线遮住。

具体错误：
1. 验收过早聚焦"数据到了没有"，没有把"锚在笔开启时仍可见"作为强制可视化断言。
2. 锚与笔都使用 `LineSeries`，当 series 重建顺序变化时，锚层级可能落后于笔，出现"有数据但看不见"。
3. E2E 只校验了 `anchor.switch` 数量，未校验锚绘图层存在与绘制数量。

## 根因

1. 把"锚可见性"当作数据问题处理，忽略了渲染层级问题。
2. 缺少"锚图层不被覆盖"的独立渲染保障。
3. E2E 只校验了数据存在性，未校验可视化存在性。

## 解法

- 在 `ChartView` 中为 `anchor.*` 增加独立顶层 canvas 渲染，不再与 pen 共享 `LineSeries` 层级竞争。
- 使用 `VITE_ENABLE_ANCHOR_TOP_LAYER` 做前端开关（默认 `1`），保留可回退路径。
- 为验收加可观测断言：`data-anchor-top-layer="1"`、`data-anchor-top-layer-path-count > 0`。
- 保留原有后端锚语义与指针规则，避免"修显示时改语义"。

## 为什么有效

- 顶层 canvas 在 DOM 层级上独立，天然避免 series 重建顺序导致的遮挡。
- 可视化不变量被显式编码为自动化断言，减少"看起来像偶发"的回归。
- 语义和绘制层解耦，后续调整 pen 样式时不会再隐式影响锚可见性。

## 检查清单

**开发前**
- [ ] 先区分"数据缺失"与"渲染遮挡"两类故障路径。
- [ ] 明确该类要满足的可视化不变量：`pen on` 时锚仍清晰可见。
- [ ] 为视觉不变量准备可自动断言的 DOM 指标（例如 `data-*`）。

**开发中**
- [ ] 锚与笔分层渲染，避免依赖 series 创建顺序。
- [ ] 新增 feature flag（默认开）并保证降级路径可回退。
- [ ] 保持锚语义不变：锚仍是指向笔的指针，不重复造笔。
- [ ] 当图上出现"数据在但看不见"时，优先评估是否应拆分到顶层画布。

**验收时**
- [ ] `pytest -q` 必过。
- [ ] `cd frontend && npm run build` 必过。
- [ ] E2E 增加"锚顶层开启 + 有路径绘制"断言并留截图。
- [ ] 对所有关键可视化要素，补一条 `data-*` 可观测指标并进 E2E 断言。

## 关联

- `frontend/src/widgets/ChartView.tsx`
- `frontend/e2e/market_kline_sync.spec.ts`
- 验证命令：
  - `pytest -q`
  - `cd frontend && npm run build`
  - `bash scripts/e2e_acceptance.sh --reuse-servers --skip-playwright-install --skip-doc-audit -- frontend/e2e/market_kline_sync.spec.ts -g "live chart loads catchup and follows WS"`
