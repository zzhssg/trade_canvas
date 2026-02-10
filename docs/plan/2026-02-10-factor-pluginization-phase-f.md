---
title: Factor 完全插件化（Phase F：Overlay 渲染插件化）
status: done
owner: codex
created: 2026-02-10
updated: 2026-02-10
---

## 目标

- 把 overlay 写路径从 orchestrator 内部硬编码渲染逻辑下沉到插件。
- 让 marker / pen / structure 三类绘图指令可分治演进，减少后续新增因子时的改动耦合。
- 保持现有 draw delta 消费契约不变。

## 变更范围

- 新增 overlay 渲染插件：
  - `/Users/rick/code/trade_canvas/backend/app/overlay_renderer_plugins.py`
  - 引入 `OverlayRenderContext` / `OverlayRenderOutput` / `OverlayRendererPlugin`。
  - 默认插件：
    - `overlay.marker`（pivot + anchor.switch markers）
    - `overlay.pen`（pen.confirmed polyline）
    - `overlay.structure`（zhongshu/alive-dead + anchor current/history + pen preview）
- orchestrator 接入插件调度：
  - `/Users/rick/code/trade_canvas/backend/app/overlay_orchestrator.py`
  - 新增渲染插件 registry + graph 拓扑调度；
  - ingest 阶段改为“采集因子事件 -> 构造 context -> 运行渲染插件 -> 落盘 overlay 指令”。
- 新增回归测试：
  - `/Users/rick/code/trade_canvas/backend/tests/test_overlay_renderer_plugins.py`
  - 覆盖默认插件图、marker 输出、pen polyline、structure 基础行为。
- 文档同步：
  - `/Users/rick/code/trade_canvas/docs/core/factor-modular-architecture.md`

## 验收

- `pytest -q backend/tests/test_overlay_renderer_plugins.py backend/tests/test_draw_delta_api.py backend/tests/test_world_state_frame_api.py backend/tests/test_world_delta_poll_api.py`（22 passed）
- `pytest -q`（196 passed）
- `bash docs/scripts/doc_audit.sh`（pass）
- `bash scripts/e2e_acceptance.sh --reuse-servers`（失败，当前基线存在 8 条与本改动无关用例失败；证据见 `output/playwright/`）

## 回滚

- 单提交回滚：`git revert <sha>`
- 最小文件回退：
  - `/Users/rick/code/trade_canvas/backend/app/overlay_orchestrator.py`
  - `/Users/rick/code/trade_canvas/backend/app/overlay_renderer_plugins.py`
  - `/Users/rick/code/trade_canvas/backend/tests/test_overlay_renderer_plugins.py`
