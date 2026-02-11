---
title: market mainflow comprehensive e2e
status: 待验收
owner: codex
created: 2026-02-11
updated: 2026-02-11
---

## 背景

- 现有 E2E 已覆盖局部能力（catchup、batch、forming、layout、replay），但缺一条“从输入到读模型再到前端可视化”的单故事闭环。
- 最近后端修复了 supervisor 重启、ws 订阅幂等等稳定性问题，需要一条端到端故事来守住“不回归”。
- 目标是让验收时能用一条测试同时回答三个问题：链路是否通、结果是否一致、同输入是否可复现。

## 目标 / 非目标

### 目标
- 新增一条 Playwright E2E，用单一 `series_id` 打通：
  - `candle_closed ingest -> /api/frame/live -> ws 增量 -> /api/factor/slices -> /api/frame/at_time`
- 每一步都给具体数值断言（`candle_time`、`candle_id`、`close`）。
- 增加一次“同输入重复读取”的稳定性断言，验证 read path 结果确定性。

### 非目标
- 本轮不扩展新的 HTTP/WS 协议字段。
- 本轮不引入 UI 交互路径的新功能（仅门禁增强）。
- 本轮不改后端生产逻辑（仅测试与文档）。

## E2E 用户故事（主链路）

### Story ID / Test Case
- Story ID: `2026-02-11/market-mainflow/comprehensive-consistency`
- Plan: `docs/plan/2026-02-11-market-mainflow-comprehensive-e2e.md`
- Test file: `frontend/e2e/market_mainflow_comprehensive.spec.ts`
- Test name: `mainflow comprehensive: ingest -> frame -> ws -> factor stays consistent @mainflow`
- Runner: Playwright（通过 `scripts/e2e_acceptance.sh` 启动 FE/BE）

### Persona / Goal
- Persona：研究员
- Goal：确认同一份 closed candle 输入在后端读模型与前端图表保持一致，并且重复读取结果稳定。

### Entry / Exit
- Entry：
  - 写入 `series_id=binance:futures:TCMAIN.../USDT:1m`
  - 预置 closed candles：`1700000000,1700000060,1700000120`
- Exit：
  - 前端图表 `data-last-time` 追到 `1700000180`
  - `/api/factor/slices` 返回 `candle_id=<series_id>:1700000180`
  - `/api/frame/at_time` 的 `time.candle_id`、`factor_slices.candle_id`、`draw_state.to_candle_time` 与同一时间点一致

### Main Flow（步骤 + 断言）
1) 预置历史闭合 K 线  
   - Action：HTTP POST `/api/market/ingest/candle_closed` 写入 3 根  
   - Assert：后续 `/api/frame/live` 与 `/api/market/candles` 都对齐到 `1700000120`

2) 打开 `/live` 并完成冷启动  
   - Action：页面加载并订阅 ws  
   - Assert：`/api/frame/live` 返回 `time.candle_id=<series_id>:1700000120`；图表 `data-last-time=1700000120`

3) 增量写入新闭合 K 线  
   - Action：再写入 `1700000180 close=44`  
   - Assert：
     - ws 收到 `candle_closed`，`candle_time=1700000180`
     - 图表 `data-last-time=1700000180`
     - 图表 `data-last-close=44`

4) 读模型一致性与可复现  
   - Action：连续两次 GET `/api/factor/slices`（`at_time=1700000180`）  
   - Assert：两次响应 JSON 完全一致，且 `candle_id=<series_id>:1700000180`

5) 世界帧一致性  
   - Action：GET `/api/frame/at_time?at_time=1700000180`  
   - Assert：
     - `time.candle_id=<series_id>:1700000180`
     - `factor_slices.candle_id=<series_id>:1700000180`
     - `draw_state.to_candle_time=1700000180`

## 变更文件

- 新增：`frontend/e2e/market_mainflow_comprehensive.spec.ts`
- 新增：`docs/plan/2026-02-11-market-mainflow-comprehensive-e2e.md`

## 验收命令

- `cd frontend && npm run build`
- `E2E_BACKEND_PORT=18080 E2E_FRONTEND_PORT=15180 E2E_SKIP_DOC_AUDIT=1 bash scripts/e2e_acceptance.sh -- --grep "@mainflow"`

## 风险与回滚

- 风险：
  - E2E 对环境稳定性要求高，若本地端口占用或缓存污染可能导致偶发失败。
- 回滚：
  - 可直接删除新增 spec 与 plan（纯测试变更，可单独 `git revert`）。

## 变更记录

- 2026-02-11：创建计划并落地 comprehensive mainflow E2E。
