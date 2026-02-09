---
title: "E2E 无结论时的止血手册（drift 判别 + 环境隔离）"
status: done
created: 2026-02-02
updated: 2026-02-09
---

# E2E 无结论时的止血手册（drift 判别 + 环境隔离）

## 问题背景

目标是"对齐老系统 factor 相关能力，做更干净简洁的架构，并给全链路 E2E"。过程中产出了不少可用代码与契约，但迟迟没有"结论"，核心原因是最终门禁（`scripts/e2e_acceptance.sh`）一直没稳定通过。

具体错误：
1. **门禁入口漂移**：E2E 用例仍在等 `plot_delta`，但前端已切换为 `overlay_delta`（后统一为 `draw_delta`，旧接口已于 2026-02-05 删除）。`market_kline_sync.spec.ts` 断言 `data-pivot-count > 0` 超时。
2. **环境隔离不足**：共享 DB / 端口冲突 / localStorage 状态导致"跑出来的不是我以为的场景"。DB 污染使不同 spec 注入的数据互相残留；端口冲突导致脚本直接失败。
3. **测试用例没有跟着契约变化同步演进**：从 `plot_delta` 迁移到 `overlay_delta` 再到 `draw_delta`，E2E 断言与等待点未同步更新。

## 根因

1. **E2E 门禁没被当成唯一真源**：主链路端点/前端数据源变更后，E2E 用例没有同步升级，导致一直失败但看起来像"实现没做好"。
2. **测试隔离缺失**：同一个 sqlite 被多个 spec 共享，跨用例数据残留让断言不稳定。
3. **缺少"快速判别证据"**：E2E log 没有强制输出关键 endpoint 命中情况，drift 只能靠 trace 人肉查。

## 解法

1. **先看"关键 endpoint 是否命中"来判别 drift**：保存 e2e_acceptance 全量日志，快速命令：`rg -n "GET /api/draw/delta|GET /api/market/candles" output/e2e_acceptance_*.log`。
2. **再做环境隔离**：端口固定非默认端口跑 e2e（`E2E_BACKEND_PORT=18000 E2E_FRONTEND_PORT=15173`）；DB 每个 spec 或每个 worker 使用独立 sqlite。
3. **用"可见的 UI data-attributes"做断言，但必须与契约同步**：数据源收敛到 `draw_delta` 后，E2E 必须断言 `/api/draw/delta` 命中，旧断言应移除。

## 为什么有效

- drift 与隔离是两类完全不同的问题：先判别类别能把排障时间从小时级降到分钟级。
- 端口/DB/localStorage 隔离后，E2E 失败才更可能是"真实逻辑错误"，而不是环境噪声。

## 检查清单

**开发前**
- [ ] 明确本次 E2E 的"唯一入口与唯一数据源"，写到 plan 的 E2E 用户故事里。
- [ ] 明确 E2E 使用的 DB 是否需要"每个 spec 一个 db"（推荐），不要默认共享。
- [ ] 明确端口策略：优先固定一组不冲突端口（如 18000/15173），写入脚本或 runbook。

**开发中**
- [ ] 每次改动主链路端点时，同步改 E2E：断言点必须贴合契约。
- [ ] 强制留 1 条"能失败"的断言：比如 `data-pivot-count` 为 0 时输出最近一次请求的 URL/状态码。
- [ ] 给 E2E 增加"关键 endpoint 命中"的日志/断言。

**验收时**
- [ ] `python3 -m pytest -q` 通过。
- [ ] `bash scripts/e2e_acceptance.sh` 通过，`output/playwright/` 中无失败 trace。
- [ ] 若 E2E 失败，先判断是"门禁漂移"还是"逻辑 bug"：检查 log 是否命中关键 endpoint。

**触发条件**（出现以下任一情况按本手册执行）：
- E2E 失败但截图看起来"页面是正常的"
- 同一个 E2E 在不同机器/不同时间表现不一致
- 改了主链路 endpoint / 前端数据源 / websocket 行为

## 关联

- `scripts/e2e_acceptance.sh`
- `output/playwright/`
- `output/e2e_acceptance_*.log`
