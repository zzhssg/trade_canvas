---
title: Factor 完全插件化（Phase I：Draw Delta 一致性校验插件化）
status: 待验收
owner: codex
created: 2026-02-10
updated: 2026-02-10
---

## 背景

Phase H 已完成 overlay 渲染归桶插件化与 freqtrade signal 插件化，但 `/api/draw/delta` 首帧自愈逻辑仍在 `draw_routes.py` 内手写 anchor/zhongshu 判定分支，新增结构性校验仍需改路由主流程。

## 目标 / 非目标

目标：
- 将 draw delta 首帧一致性校验抽象为插件，支持按需扩展校验规则而不改路由主流程。
- 保持现有“异常时重建 overlay”的行为与回归测试结果不变。

非目标：
- 不调整 draw delta 协议，不变更 overlay 指令结构。

## 方案概述

1) 新增 `overlay_integrity_plugins.py`，定义 `OverlayIntegrityPlugin` 与默认检查器。
2) `draw_routes.py` 改为调用插件评估结果决定是否重建 overlay。
3) 补 `test_overlay_integrity_plugins.py`，并回归 `test_draw_delta_api.py`。
4) 同步 core 架构与契约文档。

## 验收标准

- `pytest -q --collect-only`
- `pytest -q backend/tests/test_overlay_integrity_plugins.py backend/tests/test_draw_delta_api.py backend/tests/test_overlay_renderer_plugins.py`
- `pytest -q`
- `bash docs/scripts/doc_audit.sh`

## E2E 用户故事（门禁）

- Persona：回放/实盘读路径维护者。
- 入口：请求 `GET /api/draw/delta?cursor_version_id=0`，但 overlay 已被篡改（例如缺失 `anchor.current` 或插入伪造 `zhongshu.*` 指令）。
- 主链路：draw route 读取 factor_slices + latest overlay defs → integrity plugins 判定 mismatch → 触发 overlay 重建 → 返回修复后的 draw delta。
- 出口断言：
  - 缺失 `anchor.current` 时可恢复；
  - `zhongshu` 存在性/签名不一致时可恢复；
  - 未发生 mismatch 时不触发多余重建。

## 回滚

- 单提交回滚：`git revert <sha>`
- 最小文件回退：
  - `/Users/rick/code/trade_canvas/backend/app/overlay_integrity_plugins.py`
  - `/Users/rick/code/trade_canvas/backend/app/draw_routes.py`
  - `/Users/rick/code/trade_canvas/backend/tests/test_overlay_integrity_plugins.py`
