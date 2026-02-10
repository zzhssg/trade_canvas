---
title: E2E 门禁环境固定（禁用自动尾部回补/CCXT）
status: done
owner: codex
created: 2026-02-10
updated: 2026-02-10
---

## 目标

- 修复 `scripts/e2e_acceptance.sh` 在全量 E2E 中出现的 30s 超时与不稳定。
- 避免门禁继承 `dev_backend.sh` 默认配置导致 `/api/market/candles` 阻塞（自动尾部回补 + CCXT 回补）。
- 保持 E2E 环境可复现、可重复、与业务主链路断言一致。

## 变更范围

- 脚本固定关键环境变量（仅脚本自启服务路径生效）：
  - `/Users/rick/code/trade_canvas/scripts/e2e_acceptance.sh`
  - 新增导出：
    - `TRADE_CANVAS_ENABLE_MARKET_GAP_BACKFILL=0`
    - `TRADE_CANVAS_ENABLE_MARKET_AUTO_TAIL_BACKFILL=0`
    - `TRADE_CANVAS_ENABLE_CCXT_BACKFILL=0`
    - `TRADE_CANVAS_MARKET_HISTORY_SOURCE=""`
  - 复用服务模式新增严格预检（默认开启）：
    - `--reuse-servers` + `E2E_REUSE_STRICT=1` 时，先探测 `/api/market/candles` 与 `/api/backtest/strategies`，不满足门禁假设直接 fail-fast。
    - 提供 `--no-reuse-strict` 作为临时降级开关。
  - 新增可复用预检脚本：
    - `/Users/rick/code/trade_canvas/scripts/e2e_preflight.sh`
    - `e2e_acceptance.sh` 与 `worktree_acceptance.sh` 共用该脚本，避免门禁逻辑重复维护。
  - worktree 验收脚本新增可选预检：
    - `/Users/rick/code/trade_canvas/scripts/worktree_acceptance.sh --run-e2e-preflight`
- 工作流文档同步：
  - `/Users/rick/code/trade_canvas/docs/core/agent-workflow.md`
  - 说明 `--reuse-servers` 不覆盖已运行服务环境，且默认启用严格预检。

## 验收

- `pytest -q --collect-only`
- `cd frontend && npx tsc -b --pretty false --noEmit`
- `E2E_BACKEND_PORT=18084 E2E_FRONTEND_PORT=15184 bash scripts/e2e_acceptance.sh --skip-playwright-install --skip-doc-audit`
- `bash docs/scripts/doc_audit.sh`

## 回滚

- 单提交回滚：`git revert <sha>`。
- 最小回滚文件：
  - `/Users/rick/code/trade_canvas/scripts/e2e_acceptance.sh`
  - `/Users/rick/code/trade_canvas/docs/core/agent-workflow.md`
