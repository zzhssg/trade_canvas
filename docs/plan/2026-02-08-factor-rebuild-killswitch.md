---
title: Factor rebuild 高风险能力 kill-switch
status: 已完成
owner: codex
created: 2026-02-08
updated: 2026-02-08
---

## 目标
- 为 `POST /api/factor/rebuild` 增加高风险能力开关。
- 默认关闭，避免共享环境误触发重建。

## 方案
- 新增环境变量 `TRADE_CANVAS_ENABLE_FACTOR_REBUILD`（默认关闭）。
- 接口未开启时返回 `404 not_found`。
- 测试覆盖开关开启与关闭行为。

## 验收
- `pytest -q`
- `cd frontend && npm run build`
- `bash docs/scripts/doc_audit.sh`
