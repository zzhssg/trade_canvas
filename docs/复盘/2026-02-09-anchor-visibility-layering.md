# 锚绘图可见性复盘（layering）

## 背景

- 任务链路：`BTC 4h` 锚切换语义修复后，用户反馈“4h 图仍看不到锚绘图”。
- 涉及文件：`frontend/src/widgets/ChartView.tsx`、`frontend/e2e/market_kline_sync.spec.ts`。
- 现象证据：
  - `data-anchor-count > 0`，说明锚指令已到前端；
  - 但主图上视觉不稳定，锚线会被笔线遮住。

## 具体错误

- 验收过早聚焦“数据到了没有”，没有把“锚在笔开启时仍可见”作为强制可视化断言。
- 锚与笔都使用 `LineSeries`，当 series 重建顺序变化时，锚层级可能落后于笔，出现“有数据但看不见”。

## 影响与代价

- 用户会误判锚逻辑错误，增加排查成本。
- 图表语义和实际策略状态割裂，影响验收可信度。
- 后续每次改 pen 渲染时，都可能再次引入同类回归。

## 根因

1. 把“锚可见性”当作数据问题处理，忽略了渲染层级问题。
2. 缺少“锚图层不被覆盖”的独立渲染保障。
3. E2E 只校验了 `anchor.switch` 数量，未校验锚绘图层存在与绘制数量。

## 如何避免（检查清单）

### 开发前

- [ ] 先区分“数据缺失”与“渲染遮挡”两类故障路径。
- [ ] 明确该类要满足的可视化不变量：`pen on` 时锚仍清晰可见。
- [ ] 为视觉不变量准备可自动断言的 DOM 指标（例如 `data-*`）。

### 开发中

- [ ] 锚与笔分层渲染，避免依赖 series 创建顺序。
- [ ] 新增 feature flag（默认开）并保证降级路径可回退。
- [ ] 保持锚语义不变：锚仍是指向笔的指针，不重复造笔。

### 验收时

- [ ] `pytest -q` 必过（防主链路回归）。
- [ ] `cd frontend && npm run build` 必过（防前端类型/构建回归）。
- [ ] E2E 增加“锚顶层开启 + 有路径绘制”断言并留截图。

## 关联

- 关键实现：`frontend/src/widgets/ChartView.tsx`
- 回归断言：`frontend/e2e/market_kline_sync.spec.ts`
- 验证命令：
  - `pytest -q`
  - `cd frontend && npm run build`
  - `bash scripts/e2e_acceptance.sh --reuse-servers --skip-playwright-install --skip-doc-audit -- frontend/e2e/market_kline_sync.spec.ts -g "live chart loads catchup and follows WS"`
