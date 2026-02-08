---
title: Pen 未确认双段与白色样式对齐
status: in_progress
owner: rick
created: 2026-02-07
updated: 2026-02-07
---

## 背景
- 现有笔展示存在两处偏差：普通笔颜色为紫色；未确认笔仅有 candidate 一段，缺少 extending。
- 参考 trade_system 口径，需要把未确认笔拆成 extending + candidate（均为 head、可重绘、虚线）。

## 目标 / 非目标
### 目标
- 普通笔（`pen.confirmed`）统一为白色实线（history）。
- 未确认笔包含两段：`pen.extending` 和 `pen.candidate`，均为白色虚线（head）。
- 计算口径对齐：extending 从倒数第二个有效 major pivot 出发；candidate 从 extending 终点再反向取极值。

### 非目标
- 不改 pivot/confirmed pen 的确认规则。
- 不改 anchor 颜色（继续用橙色强调）。

## 方案概述
- 后端统一实现 `build_pen_head_preview()`，产出 `head.extending/head.candidate`，并复用到 factor slice、head snapshot、overlay。
- 去掉 `factor_slices_service` 内重复候选笔计算，避免双口径漂移。
- 前端保留 anchor 高亮，普通笔渲染色改白；新增 pen 子特征 `pen.extending`、`pen.candidate`。

## 里程碑
- M1: 后端计算与 overlay 出图口径统一。
- M2: 前端样式与特征开关对齐。
- M3: 回归测试 + 门禁。

## 任务拆解
- [x] 抽取统一 pen head 预览逻辑（extending/candidate）。
- [x] factor slices / factor head / overlay 复用统一逻辑。
- [x] 前端普通笔白色 + 新增未确认笔子特征。
- [x] 补回归测试（pen head 语义 + draw delta 样式/线型）。

## 风险与回滚
- 风险：未确认笔口径变更可能影响 anchor 基于 candidate 的可视语义。
- 回滚：单 commit 可 `git revert <sha>`；无需数据迁移。

## 验收标准
- `pytest -q` 通过。
- `cd frontend && npm run build` 通过。
- draw delta 返回：
  - `pen.confirmed.color == "#ffffff"` 且实线；
  - `pen.extending/pen.candidate` 为白色虚线；
  - `candidate.start_time == extending.end_time`。

## E2E 用户故事（门禁）
- Persona: 交易研究员在 Live 图查看结构笔。
- Goal: 在同一根 closed candle 对齐下，区分 history confirmed 与 head 未确认双段。
- Flow:
  1) 写入固定 K 线序列（可复现）。
  2) 拉取 `/api/draw/delta`，验证 `pen.confirmed`、`pen.extending`、`pen.candidate` 三类线。
  3) 拉取 `/api/factor/slices`，验证 `pen.head` 中 extending/candidate 的时间衔接关系。
- 断言：
  - confirmed 白色实线；
  - extending/candidate 白色虚线；
  - candidate 起点等于 extending 终点；
  - 所有端点 `time <= at_time`（无未来函数）。

## 变更记录
- 2026-02-07: 将占位稿补全为可执行 plan（pen 未确认双段 + 白色样式）。
