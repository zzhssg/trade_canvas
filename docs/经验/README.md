---
title: 经验索引（docs/经验）
status: done
created: 2026-02-02
updated: 2026-02-14
---

# 经验索引（docs/经验）

目标：把“踩坑记录”变成可检索的工程资产，支持快速定位相似问题与复用解法。

## 目录使用规则

- 文件命名：`YYYY-MM-DD-<slug>.md`（kebab-case，英文短词）。
- 新增经验后，必须同步更新本索引（至少补 1 个标签与 1 条入口）。
- 经验文档建议包含：问题背景 / 根因 / 解法 / 为什么有效 / 检查清单 / 关联命令与产物。

## 快速检索（先用命令定位）

```bash
# 按关键词检索经验
rg -n "e2e|playwright|ws|ingest|candle_id|fitcontent" docs/经验

# 只看文件名（快速扫主题）
ls -1 docs/经验 | sort
```

## 标签索引（按问题类型）

### E2E / Playwright / 门禁

- `2026-02-02-e2e-fast-feedback-loop.md`
- `2026-02-02-e2e-isolation-playbook.md`
- `2026-02-02-playwright-trace-root-cause.md`
- `2026-02-02-smoke-vs-sot-boundary.md`
- `2026-02-03-wheel-scroll-e2e-guardrails.md`
- `2026-02-11-e2e-shutdown-cancel-tasks-drain.md`

### 图表渲染 / 交互

- `2026-02-02-chart-fitcontent-guardrails.md`
- `2026-02-02-history-solid-head-dashed.md`
- `2026-02-09-anchor-top-layer-rendering.md`

### 数据口径 / 主链路一致性

- `2026-02-02-candle-id-alignment-e2e.md`
- `2026-02-03-point-query-must-check-head-ready.md`
- `2026-02-08-gap-backfill-killswitch-pattern.md`

### 调试与流程

- `2026-02-02-debug-hang-playbook.md`
- `2026-02-02-draw-delta-compat-rollout.md`
- `2026-02-02-trade-system-factor2-pipeline-notes.md`

## 模块入口（按代码边界）

- `frontend/` 相关：优先看 `chart-fitcontent-guardrails`、`wheel-scroll-e2e-guardrails`、`anchor-top-layer-rendering`
- `backend/market|ingest` 相关：优先看 `e2e-isolation-playbook`、`gap-backfill-killswitch-pattern`、`point-query-must-check-head-ready`
- `contracts/口径` 相关：优先看 `candle-id-alignment-e2e`、`smoke-vs-sot-boundary`

## 与 skills 的联动

- 交付后经验提炼：`tc-learning-loop`
- 复盘类专题：`tc-fupan`
- 若某类经验复用稳定（高置信度），进入 `tc-skill-authoring` 升级为项目 skill。
