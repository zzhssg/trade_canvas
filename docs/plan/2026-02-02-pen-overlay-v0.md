---
title: Pen Overlay v0（前端绘制确认笔）
status: done
owner:
created: 2026-02-02
updated: 2026-02-02
---

## 背景

后端已具备 v0 的 FactorStore/FactorLedger：
- `pivot.major`（延迟确认，history）
- `pen.confirmed`（确认笔，history，延迟到“下一根反向 pivot”可见）

但前端目前只画 pivot markers（来自 `GET /api/draw/delta`），没有把确认笔画出来。

## 目标 / 非目标

### 目标（Do）
- 前端在 Live 图中绘制 `pen.confirmed`（折线/线段）。
- 数据来源：`GET /api/factor/slices?series_id&at_time`（不引入新协议）。
- 保持实现精简：只画 confirmed（append-only），不做复杂 head/修订。

### 非目标（Don’t）
- 不引入 slot-delta/replay 协议。
- 不画 forming pen / extending pen（后续再做）。

## 方案概述

- 新增前端 feature：`pen.confirmed`（FactorPanel 可开关）
- Chart 渲染：
  - 拉取 `snapshots.pen.history.confirmed`
  - 将 confirmed pens 还原成折线路径点：
    - 首笔：push(start_time,start_price)
    - 每笔：push(end_time,end_price)（与上一笔端点相同则去重）
  - 用一个 `LineSeries` 绘制（confirmed 本身是链式结构，连续折线符合语义）

## E2E 用户故事（门禁）

Persona/Goal：策略开发者打开 live 图，能看到确认笔线段不空白且不会引起页面崩溃。

断言：
- 现有 Playwright suite 继续通过（不额外增加 flaky UI 断言）。

命令：
- `python3 -m pytest -q`
- `E2E_PLAN_DOC="docs/plan/2026-02-02-pen-overlay-v0.md" bash scripts/e2e_acceptance.sh`

## 变更记录
- 2026-02-02: 创建（开发中）
- 2026-02-02: 验收通过（pytest + Playwright E2E + plan status gate），状态更新为 done
