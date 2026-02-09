---
title: "E2E 快反馈 + 最终门禁分层（避免 41s 全量阻塞迭代）"
status: 已完成
created: 2026-02-02
updated: 2026-02-09
---

# E2E 快反馈 + 最终门禁分层（避免 41s 全量阻塞迭代）

## 问题背景

门禁脚本 `bash scripts/e2e_acceptance.sh` 用于跑 FE+BE 集成 E2E（Playwright），单次耗时约 **41.5s**（5 个 Playwright tests，1 worker）。E2E 过程中触发大量 HTTP ingest（单个用例可达 200+ 次 `POST /api/market/ingest/candle_closed`），若端口占用还会被迫重复跑。

每次改一个断言/细节都要等 30s-1min，失败代价高（端口冲突/trace 损坏/偶发失败会迫使重复跑多次）。

## 根因

1. **E2E 造数方式是"逐根 HTTP POST"**：没有批量 ingest 的 fastpath，大量 HTTP 往返累计显著。
2. **E2E runner 默认包含"启动前后端 dev server"**：每次启动 `uvicorn` + `vite dev` 再跑 Playwright，冷启动数秒到十数秒。
3. **缺少"快跑模式"**：门禁与开发迭代共用同一套配置，因子确认窗口（如 `window_major=50`）要求更长 candle 序列来触发事件，放大造数成本。

## 解法

- **先做"语义级小集成"，再上全量 E2E**：用 `fastapi TestClient` 或 `pytest` 直接验证 `/api/draw/delta` 的可观测语义，避免每次都拉起浏览器。
- **把 E2E 造数从"长序列"改为"最短能触发语义的序列"**：通过 env 降低窗口（E2E 专用），让样本长度更短。
- **新增 batch ingest**：`POST /api/market/ingest/candles_closed`（一次传 N 根），减少 HTTP 往返。
- **支持隔离并行**：每个实例用不同端口 + 独立 sqlite DB，用 Playwright shard 拆分测试集。

## 为什么有效

- 语义级小集成只覆盖"后端契约与不变量"，成本低、失败定位清晰，适合开发期高频运行。
- 全量 E2E 留在最后作为门禁，确保 FE+BE+WS+渲染仍是同一条主链路。

## 检查清单

**开发前**
- [ ] 为 E2E 准备快跑模式 env（降低 pivot window / 关掉非关键 stream），在脚本中统一注入。
- [ ] 为 ingest 提供 batch endpoint（一次提交 N 根 closed candles）。

**开发中**
- [ ] 调试阶段优先跑单测/小集成，避免频繁全量 E2E。
- [ ] E2E 失败时先确认是否是"端口占用/trace 损坏/非业务错误"，避免误判为业务回归。
- [ ] 给 E2E 增加"只跑单测用例"的入口：`cd frontend && npx playwright test e2e/market_kline_sync.spec.ts -g "live chart"`。

**验收时**
- [ ] E2E 门禁仍跑全量，确保 cache/依赖已就绪（Playwright 浏览器已安装）。
- [ ] 交付证据附上：`/tmp/tc_e2e.log` + `output/playwright/`。

## 关联

- 全量门禁：`bash scripts/e2e_acceptance.sh`
- 本地快跑：`bash scripts/e2e_acceptance.sh --skip-playwright-install --skip-doc-audit -- --grep ...`
- 本地 smoke：`bash scripts/e2e_acceptance.sh --smoke --skip-playwright-install --skip-doc-audit`
- 后端语义集成：`python3 -m pytest -q`
- E2E 产物：`output/playwright/`
