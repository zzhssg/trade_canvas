---
name: tc-acceptance-e2e
description: "Use at the final acceptance stage of trade_canvas work (before claiming 'done' / delivery): requires FE+BE integrated Playwright E2E gate to pass (exit code 0) and requires attaching concrete evidence (commands + outputs + artifacts path)."
metadata:
  short-description: 最终验收（E2E + 证据交付）
---

# tc-acceptance-e2e（最终验收：E2E + 证据交付）

目标：在宣称“完成/可交付”之前，把 trade_canvas 的主链路验收收敛到 **唯一可复核证据**：
- `bash scripts/e2e_acceptance.sh` 退出码为 0
- `output/playwright/` 中留存 trace/screenshot/video（失败时必有，成功时可为空但要有本次运行日志）

> 本 skill 只负责“最后交付门禁”。开发过程的 E2E 用户故事写法与拆解，走 `tc-e2e-gate`。

---

## 1) Final Gate（必须通过）

### 1.1 统一跑法（推荐）

避免端口冲突与本机 dev 服务干扰，固定使用非默认端口：

```bash
E2E_BACKEND_PORT=18080 E2E_FRONTEND_PORT=15180 bash scripts/e2e_acceptance.sh
```

### 1.2 输出证据（必须给）

交付汇报至少包含：
- 命令：`E2E_BACKEND_PORT=... E2E_FRONTEND_PORT=... bash scripts/e2e_acceptance.sh`
- 关键输出：最后的 `OK: Playwright E2E passed.`（或失败栈）
- 产物路径：`output/playwright/`

---

## 2) 常见坑位（先排它再谈“逻辑没对”）

这些坑会让你“做了很多但没结论”，本质是 **环境/门禁漂移**：

1) **E2E 入口漂移（endpoint / 前端数据源变了，但 spec 还在等旧链路）**
- 快速判别：在 e2e 日志里 grep 关键 endpoint 是否命中：
  - `rg -n "GET /api/draw/delta|GET /api/market/candles" output/e2e_acceptance*.log`
- 修复原则：主链路改动（plot→overlay / slice→ledger-only）必须同步改 E2E 的断言点与等待点。

2) **DB 污染（跨用例/跨次运行残留导致断言漂移）**
- 现象：forming 测试期望 last-time=1800，实际因为 DB 已有 2700 的 candle 导致失败。
- 当前解决：`scripts/e2e_acceptance.sh` 已使用“每次运行唯一 DB”（不要 `--reuse-servers` 复用旧服务/旧 DB）。

3) **端口冲突**
- 现象：`backend port already in use: 8000` 直接退出。
- 解决：用非默认端口或先 `bash scripts/free_port.sh 8000`。

---

## 3) 失败时的最短定位流程（强制）

1) 看失败用例对应目录：`output/playwright/<test-name>-chromium/`
2) 打开 trace：
```bash
cd frontend
npx playwright show-trace ../output/playwright/<...>/trace.zip
```
3) 先判别“漂移”还是“逻辑”：
- 日志里有没有命中预期 endpoint（overlay/plot）？
- screenshot 上 UI 是否在预期路由与 series_id？
