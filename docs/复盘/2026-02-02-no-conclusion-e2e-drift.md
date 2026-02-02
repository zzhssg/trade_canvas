---
title: 本轮“用很久没结论”的根因：E2E 门禁漂移 + 测试隔离不足
status: done
created: 2026-02-02
updated: 2026-02-02
---

# 本轮“用很久没结论”的根因：E2E 门禁漂移 + 测试隔离不足

## 背景

本轮目标是“对齐老系统 factor 相关能力，做更干净简洁的架构，并给全链路 E2E”。过程中确实产出了不少可用代码与契约，但迟迟没有“结论”，核心原因是：**最终门禁（`scripts/e2e_acceptance.sh`）一直没稳定通过**，导致无法宣称 DoD 达成。

涉及链路（会互相影响）：
- 前端 `ChartView` 的数据源切换（`/api/plot/delta` → `/api/overlay/delta`）
- 后端 ingest 链路新增 orchestrator（plot/factor/overlay）
- Playwright E2E 用例对“具体 data-attributes / 默认 UI 状态”的强依赖

证据：
- E2E 失败产物：`output/playwright/`（trace/screenshot/video）
- 一次跑的完整 log：`output/e2e_acceptance_18000.log`、`output/e2e_acceptance_18111.log`

## 具体错误（可复现现象）

1) **门禁入口漂移：E2E 用例仍在等 `plot_delta`，但前端已切换为 `overlay_delta`**
- 现象：`market_kline_sync.spec.ts` 断言 `data-pivot-count > 0` 超时为 0。
- 证据：`output/e2e_acceptance_18000.log` 中只看到 `GET /api/plot/delta ...`，没有 `GET /api/overlay/delta ...`（说明 E2E 跑到的前端 bundle 并非预期版本/或脚本运行时上下文没对齐）。

2) **E2E 环境隔离不足（共享 DB / 端口冲突 / localStorage 状态）导致“跑出来的不是我以为的场景”**
- 端口冲突：8000 被占用导致脚本直接失败（需要 `scripts/free_port.sh` 或换端口）。
- DB 污染：E2E 使用同一个 sqlite（`backend/data/market_e2e.db`），不同 spec 注入的数据会互相残留，导致：
  - `market_kline_sync` 的 forming 测试期望初始 `data-last-time=1800`，实际因为 DB 已经有 2700 的 closed candle 而变成 2700。
  - `timeframe_selector` 期望 4h 最新 close=99999，但实际返回了后续注入的 28800（10001）。
- UI 状态：虽然部分 spec 用 `localStorage.clear()`，但仍有“初始化顺序/异步请求”导致的竞态（例如先收到 WS/或先渲染旧 series）。

3) **“实现正确”与“验收正确”之间缺了一个稳定桥：测试用例没有跟着契约变化同步演进**
- 例如：从 `plot_delta` 迁移到 `overlay_delta`，应同步：
  - 前端 API client 使用点
  - E2E 断言与等待点（应等待 `/api/overlay/delta` 或 UI 暴露的 overlay 计数）
  - 后端 log 采样点（出现关键 endpoint 即可快速定位 drift）

## 影响与代价

- 典型“做了很多事但无法交付”：因为最终门禁不稳 → 没法给一个可复核的结论。
- 返工主要消耗在“猜到底跑的是哪条链路/哪份 bundle/哪份 DB 数据”，而不是领域实现本身。

## 根因（1–3 条）

1) **E2E 门禁没被当成唯一真源**：当主链路端点/前端数据源变更后，E2E 用例没有同步升级，导致一直失败但看起来像“实现没做好”。  
2) **测试隔离缺失**：同一个 sqlite 被多个 spec 共享，跨用例数据残留让断言不稳定，导致“难以定位是逻辑错还是环境错”。  
3) **缺少“快速判别证据”**：E2E log 没有强制输出关键 endpoint 命中情况，导致 drift 只能靠 trace 人肉查。

## 如何避免（检查清单）

开发前：
- [ ] 明确本次 E2E 的“唯一入口与唯一数据源”（例如 `overlay_delta`），并写到 plan 的 E2E 用户故事里。
- [ ] 明确 E2E 使用的 DB 是否需要“每个 spec 一个 db”（推荐），不要默认共享。
- [ ] 明确端口策略：优先固定一组不冲突端口（例如 18000/15173），写入脚本或 runbook。

开发中：
- [ ] 每次改动主链路端点（plot→overlay / factor slices→ledger-only）时，同步改 E2E：断言点必须贴合契约。
- [ ] 强制留 1 条“能失败”的断言：比如 `data-pivot-count` 为 0 时输出最近一次 overlay 请求的 URL/状态码。
- [ ] 给 E2E 增加“关键 endpoint 命中”的日志/断言（例如必须命中 `/api/overlay/delta`）。

验收时：
- [ ] `python3 -m pytest -q` 通过（单元/集成）
- [ ] `bash scripts/e2e_acceptance.sh` 通过，并且 `output/playwright/` 中无失败 trace
- [ ] 若 E2E 失败，先判断是“门禁漂移”还是“逻辑 bug”：检查 log 是否命中关键 endpoint

