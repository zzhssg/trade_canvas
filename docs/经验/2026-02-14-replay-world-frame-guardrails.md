---
title: Replay world-frame 路径降级与请求风暴门禁经验
status: done
created: 2026-02-14
updated: 2026-02-14
---

# Replay world-frame 路径降级与请求风暴门禁经验

### [LL-2026-02-14-01] pollWorldDelta 的 409 不能直接判定为 world-frame 失效
- Trigger（何时触发）：E2E `@smoke live backfill burst does not hammer delta/slices` 偶发失败，`slicesGets` 从 1 抖到 2。
- Action（采取动作）：在 `liveSessionOverlayFollow` 中区分 HTTP 状态；`pollWorldDelta` 返回 `409` 时保持 world-frame 路径，只有非 409 才把 `worldFrameHealthyRef` 标记为 false。
- Evidence（命令 + 关键输出 + 产物路径）：`bash scripts/e2e_acceptance.sh --skip-playwright-install --skip-doc-audit -- e2e/market_kline_sync.spec.ts -g "does not hammer delta/slices" --workers=1`，修复后用例通过；产物路径 `frontend/output/playwright/history_backfill_axis_guard.png`。
- Confidence（0.3-0.9）：0.7
- Scope（适用范围）：依赖 world-frame 增量轮询的实时图表跟随路径。
- Anti-Scope（不适用范围）：后端真实不可用（5xx/网络错误）场景，仍应降级到 delta/factor-slices 兜底。
- Next-Check（下次如何复核）：复跑 `bash scripts/e2e_acceptance.sh --smoke --skip-playwright-install --skip-doc-audit` 并确认 `market_kline_sync` 不再触发 `slicesGets > 1`。

### [LL-2026-02-14-02] Hook 导出回调要避免对象依赖抖动
- Trigger（何时触发）：`useReplayOverlayRuntime` 回调依赖包含对象，导致上游 effect 反复触发并放大请求次数。
- Action（采取动作）：用 `ref` 存最新参数，导出稳定 callback（空依赖），在回调内读取 `ref.current`。
- Evidence（命令 + 关键输出 + 产物路径）：`cd frontend && npm run build`（通过，且无 chunk 循环警告）；`cd frontend && npm run test:unit`（4 passed）；产物路径 `frontend/output/playwright/live_browse_MLM9WMI6_01_initial_btc_1m.png`。
- Confidence（0.3-0.9）：0.6
- Scope（适用范围）：参数多、且被多个 effect 透传的 runtime callback 组合器。
- Anti-Scope（不适用范围）：回调必须随依赖变化而语义变化的业务逻辑（不能盲目“稳定化”）。
- Next-Check（下次如何复核）：在相关 hook 修改后，重点观察 E2E 请求计数类门禁（delta/slices/health）是否回归抖动。
