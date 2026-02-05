---
title: E2E 迟迟无结论时的止血手册（先判别 drift，再隔离环境）
status: draft
created: 2026-02-02
updated: 2026-02-05
---

# E2E 迟迟无结论时的止血手册（先判别 drift，再隔离环境）

## 场景与目标

场景：你感觉“实现差不多了”，但 `bash scripts/e2e_acceptance.sh` 总不过，导致长时间没有结论。

目标：把排查从“人肉猜”变成 10 分钟内可判别的工程流程：
- 先判断是 **E2E 入口漂移**（跑的不是预期链路/预期 bundle）
- 再处理 **测试隔离**（DB/端口/localStorage 的污染）

## 做对了什么（可复用动作）

1) 先看“关键 endpoint 是否命中”来判别 drift
- 产物：保存一份 e2e_acceptance 全量日志（例如 `output/e2e_acceptance_*.log`）
- 快速命令（示例）：
  - `rg -n "GET /api/draw/delta|GET /api/market/candles" output/e2e_acceptance_*.log`

2) 再做环境隔离（避免跨用例互相污染）
- 端口：固定非默认端口跑 e2e，避免被本机开发服务占用
  - 示例：`E2E_BACKEND_PORT=18000 E2E_FRONTEND_PORT=15173 bash scripts/e2e_acceptance.sh`
- DB：每个 spec 或每个 worker 使用独立 sqlite（最稳），至少每次 run 清空 DB
  - 当前脚本会为每次 run 生成独立 sqlite（`backend/data/market_e2e_<port>_<ts>_<pid>.db`）；如果使用 `--reuse-servers` 复用服务，需要你自己保证 DB 隔离

3) 用“可见的 UI data-attributes”做断言，但必须与契约同步
- 如果 Chart 数据源从旧接口收敛到 `draw_delta`：
  - E2E 必须断言 `/api/draw/delta` 命中（或 UI 提供 draw/overlay 计数）
  - 旧的 `plot_delta/overlay_delta` 断言应移除（旧接口已于 2026-02-05 删除）

## 为什么有效

- drift 与隔离是两类完全不同的问题：先判别类别能把排障时间从小时级降到分钟级。
- 端口/DB/localStorage 隔离后，E2E 失败才更可能是“真实逻辑错误”，而不是环境噪声。

## 复用方式（下一次怎么触发）

- 当出现以下任一情况就按本手册执行：
  - E2E 失败但截图看起来“页面是正常的”
  - 同一个 E2E 在不同机器/不同时间表现不一致
  - 改了主链路 endpoint / 前端数据源 / websocket 行为

## 关联

- 复盘根因：`docs/复盘/2026-02-02-no-conclusion-e2e-drift.md`
- 门禁脚本：`scripts/e2e_acceptance.sh`
- 证据目录：`output/playwright/`
