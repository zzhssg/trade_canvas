---
title: 经验：把 E2E 从“门禁”拆成“快反馈 + 最终门禁”
status: 已完成
owner:
created: 2026-02-02
updated: 2026-02-02
---

## 场景与目标

场景：E2E（Playwright）覆盖 FE+BE 主链路，但单次耗时在 30s+，导致开发迭代慢。

目标：保持门禁强度不降低的前提下，把日常迭代的反馈回路缩短到秒级/十秒级。

## 做对了什么（可复用动作）

- **先做“语义级小集成”，再上全量 E2E**：
  - 用 `fastapi TestClient` 或 `pytest` 直接验证 `/api/overlay/delta` 的可观测语义（active_ids/patch/对齐），避免每次都拉起浏览器。
- **把 E2E 的造数从“长序列”改为“最短能触发语义的序列”**：
  - 对于 pivot/pen 等 delayed 可见性产物，优先通过 env 降低窗口（E2E 专用），让样本长度更短。

## 为什么有效（机制/约束）

- 语义级小集成只覆盖“后端契约与不变量”，成本低、失败定位清晰；适合开发期高频运行。
- 全量 E2E 留在最后作为门禁，确保 FE+BE+WS+渲染仍是同一条主链路。

## 复用方式（落地建议）

1) 新增 “E2E 快跑 env” 并在 `scripts/e2e_acceptance.sh` 注入（示例）：
   - `TRADE_CANVAS_PIVOT_WINDOW_MAJOR=10`
   - `TRADE_CANVAS_PIVOT_WINDOW_MINOR=3`
   - （可选）关闭与本轮无关的 stream/轮询，减少噪声

2) 把“门禁 E2E 串行”改成“按实例隔离并行”（适合多 agent / 多终端并行跑）：
   - 结论：**同一套 backend+DB 上的 E2E 应该串行**（避免互相写 DB / 抢同一个 series_id），但 **可以起多套隔离实例并行跑不同 shard/不同 spec**。
   - 做法：每个实例用不同端口（以及独立 sqlite DB），并用 Playwright shard 拆分测试集：
     - agent A：`E2E_BACKEND_PORT=18080 E2E_FRONTEND_PORT=15173 bash scripts/e2e_acceptance.sh --skip-playwright-install --skip-doc-audit -- --shard 1/3`
     - agent B：`E2E_BACKEND_PORT=18081 E2E_FRONTEND_PORT=15174 bash scripts/e2e_acceptance.sh --skip-playwright-install --skip-doc-audit -- --shard 2/3`
     - agent C：`E2E_BACKEND_PORT=18082 E2E_FRONTEND_PORT=15175 bash scripts/e2e_acceptance.sh --skip-playwright-install --skip-doc-audit -- --shard 3/3`
   - 说明：最终交付仍需跑一次完整门禁：`bash scripts/e2e_acceptance.sh`（不要长期依赖 skip-doc-audit）。

2) 新增 batch ingest（只吃 closed candle）：
   - `POST /api/market/ingest/candles_closed`（一次传 N 根）
   - E2E 与回放统一使用 batch 入口，减少 HTTP 往返

3) 给 E2E 增加“只跑单测用例”的入口：
   - `cd frontend && npx playwright test e2e/market_kline_sync.spec.ts -g \"live chart\"`

## 关联（可执行命令/产物）

- 全量门禁：`bash scripts/e2e_acceptance.sh`
- 本地快跑（跳过浏览器安装/文档审计，并透传 Playwright 参数）：`bash scripts/e2e_acceptance.sh --skip-playwright-install --skip-doc-audit -- --grep ...`
- 本地 smoke（只跑 `@smoke`）：`bash scripts/e2e_acceptance.sh --smoke --skip-playwright-install --skip-doc-audit`
- 后端语义集成（示例）：`python3 -m pytest -q`
- E2E 产物：`output/playwright/`
