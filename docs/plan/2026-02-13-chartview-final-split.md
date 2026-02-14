---
title: ChartView 最终拆分收口（A 方案）
status: 已完成
owner: Codex
created: 2026-02-13
updated: 2026-02-13
---

## 背景

`frontend/src/widgets/ChartView.tsx` 长期承载状态声明、回调组装、运行时副作用与视图渲染，文件规模超过前端拆分门禁（>400 行），阅读和回滚成本高。

## 目标 / 非目标

- 目标
  - 在不改变外部行为契约的前提下，将 `ChartView.tsx` 拆到 400 行以内。
  - 将副作用编排、回调拼装、渲染壳层下沉到独立 hook/runtime。
  - 保持 E2E 主链路可跑通（图表加载 + replay + 覆盖层）。
- 非目标
  - 不改 HTTP/WS 协议。
  - 不引入新交互或新业务能力。

## 方案概述

采用 A 方案（编排保留组件、复杂逻辑下沉 hook/runtime）：

1. 提取视图壳层：`ChartViewShell.tsx`
2. 提取 overlay/pen/replay 回调组合：`chartRuntimeCallbacks.ts` + `chartOverlayCallbacks.ts`
3. 提取 draw tool 运行时组合：`useChartDrawToolRuntime.ts`
4. 提取生命周期运行时：`chartLifecycleRuntime.ts`
5. 提取 refs/state 聚合：`useChartRuntimeRefs.ts`、`useChartViewState.ts`

## 里程碑

1. 结构拆分完成，`ChartView.tsx` 降到 400 行以内
2. 类型检查与构建通过
3. 交付说明补齐（P/R 自检、回滚路径、命令证据）

## 任务拆解

- [x] 提取 `ChartViewShell.tsx`，组件只保留数据绑定
- [x] 提取 runtime callbacks 组合 hook
- [x] 提取 draw tool 组合 hook
- [x] 提取 chart 生命周期 runtime
- [x] 引入 runtime refs/view state 聚合 hook
- [x] 通过 `npx tsc -b --pretty false --noEmit`
- [x] 通过 `npm run build`
- [x] 通过 `bash scripts/e2e_acceptance.sh --skip-playwright-install`

## 风险与回滚

- 风险
  - hook 参数拼装错误导致回放或 overlay 更新失效
  - 生命周期清理遗漏导致 series 残留
- 回滚
  - 按原子改动 `git revert <sha>` 回退新增 runtime/hook 文件与 `ChartView.tsx` 引用

## 验收标准

- `frontend/src/widgets/ChartView.tsx` < 400 行
- 前端类型检查通过
- 前端 build 通过（允许既有 chunk size warning）
- 不出现空白图表/overlay 丢失/replay 不可用

## E2E 用户故事（门禁）

- Persona：交易研究员
- 入口：打开图表并加载 `binance:futures:BTC/USDT:1m`
- 流程：切换指标显示 -> 切换周期 -> 进入 replay 并拖动索引
- 出口断言：
  - `data-candles-len > 0`
  - `data-series-id` 与选择一致
  - replay 模式下 `data-replay-index` 正常变化
  - 无错误遮罩
- 证据命令：
  - `cd frontend && npx tsc -b --pretty false --noEmit`
  - `cd frontend && npm run build`
  - （可选）`bash scripts/e2e_acceptance.sh`

## 变更记录
- 2026-02-13: 创建并开始执行拆分
- 2026-02-13: 完成 ChartView 编排层瘦身与 runtime/hook 下沉，`ChartView.tsx` 降到 391 行
- 2026-02-13: E2E 门禁全量通过（12 passed），并修正空数据回补等待时长以稳定 `ui_clicks_no_blank` 用例
- 2026-02-13: 清理未使用的 `useChartLifecycleHandlers.ts`，避免生命周期逻辑重复维护
