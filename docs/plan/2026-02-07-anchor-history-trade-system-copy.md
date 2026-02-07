---
title: 锚历史（historical anchors）对齐 trade_system 语义
status: 已完成
owner: codex
created: 2026-02-07
updated: 2026-02-07
---

## 目标
- 对齐 trade_system 锚语义：`history.anchors + history.switches` append-only 且 1:1。
- 增加“同起点仅更新，不记 switch”门禁。
- 在 overlay/frontend 增加历史锚可视化开关。

## 非目标
- 不引入 divergence 或完整 factor2 模型。
- 不改动现有 world frame / world delta API 路径。

## E2E 用户故事（门禁）
- Persona：结构研究者
- Goal：在 live 图表看到 current/history/switch 三类锚信息，且历史锚与换锚事件严格对齐。
- Flow：
  1) 注入固定 closed candles，触发多次锚切换；
  2) 读取 `/api/factor/slices`，断言 `history.anchors` 与 `history.switches` 等长且逐项对齐；
  3) 读取 `/api/draw/delta`，断言存在 `anchor.history` 指令；
  4) 前端切换 `anchor.history` 可见性，图层显隐一致。

## 验收命令
- `pytest -q`
- `cd frontend && npm run build`
- `bash docs/scripts/doc_audit.sh`
