---
title: Factor 完全插件化（Phase J：Overlay 输出统一为指令流）
status: 待验收
owner: codex
created: 2026-02-10
updated: 2026-02-10
---

## 背景

Phase H/I 后，overlay 归桶与完整性校验均已插件化，但渲染输出仍保留 `pen_def` 特例字段，`overlay_orchestrator` 需要维护一段单独写入分支。

## 目标 / 非目标

目标：
- 移除 `OverlayRenderOutput.pen_def` 特例，统一通过 `polyline_defs` 输出所有折线指令。
- 让 `overlay_orchestrator` 落库路径只保留通用 marker/polyline 写入循环。
- 保持 `pen.confirmed` 指令语义不变。

非目标：
- 不改变 draw delta 协议，不调整前端消费字段。

## 方案概述

1) `PenOverlayRenderer` 直接产出 `("pen.confirmed", visible_time, payload)` 到 `polyline_defs`。
2) `OverlayRenderOutput` 删除 `pen_def` 字段；orchestrator 删除 `pen_def` 专用落库逻辑。
3) 更新 `test_overlay_renderer_plugins.py` 并回归 `test_draw_delta_api.py`。

## 验收标准

- `pytest -q backend/tests/test_overlay_renderer_plugins.py backend/tests/test_draw_delta_api.py backend/tests/test_overlay_integrity_plugins.py`
- `pytest -q`
- `bash docs/scripts/doc_audit.sh`

## E2E 用户故事（门禁）

- Persona：图表渲染链路维护者。
- 入口：闭合 K 线流触发 `overlay_orchestrator.ingest_closed`。
- 主链路：renderer plugin 输出 marker/polyline 指令 → orchestrator 统一落盘 overlay versions → `/api/draw/delta` 返回 `pen.confirmed` 等指令。
- 出口断言：
  - `pen.confirmed` 依旧可见且点数一致；
  - orchestrator 无 `pen_def` 专用写入分支；
  - anchor/zhongshu 自愈逻辑回归通过。

## 回滚

- 单提交回滚：`git revert <sha>`
- 最小文件回退：
  - `/Users/rick/code/trade_canvas/backend/app/overlay_renderer_plugins.py`
  - `/Users/rick/code/trade_canvas/backend/app/overlay_orchestrator.py`
  - `/Users/rick/code/trade_canvas/backend/tests/test_overlay_renderer_plugins.py`
