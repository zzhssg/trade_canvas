---
title: Factor 逻辑哈希门禁（代码变更触发数据失效）
status: 已完成
owner: codex
created: 2026-02-07
updated: 2026-02-07
---

## 目标
- 为 factor 数据增加可验证的 `logic_hash` 指纹。
- 当代码/关键参数变更后，读路径拒绝消费旧 factor 数据（409 fail-safe）。

## 实现范围
- `factor_series_state` 增加 `logic_hash` 列（兼容旧库自动迁移）。
- `factor_orchestrator` 在写入 head_time 时同步写入 `logic_hash`。
- `/api/factor/slices`、`/api/frame/*`、`/api/delta/poll` 增加逻辑哈希校验门禁。

## 验收
- `pytest -q`
- `cd frontend && npm run build`
- `bash docs/scripts/doc_audit.sh`
