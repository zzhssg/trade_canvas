---
title: E2E 收尾阶段 Cancel running tasks 的定位与收敛
status: done
created: 2026-02-11
updated: 2026-02-11
---

# E2E 收尾阶段 Cancel running tasks 的定位与收敛

## 现象

在 `scripts/e2e_acceptance.sh` 跑完且 Playwright 用例全部通过后，日志尾部仍偶发：

- `ERROR: Cancel 23 running task(s), timeout graceful shutdown exceeded`

这会干扰验收判断，容易把“收尾噪音”误判成“功能失败”。

## 根因定位（本次复盘）

### 1) 证据链

- 现象日志（旧）：
  - `output/e2e_acceptance_2026-02-11-backend-hardening-final-v5.log`
- 对照实验（跳过 docs audit）：
  - 运行：
    - `E2E_SKIP_DOC_AUDIT=1 E2E_BACKEND_PORT=18080 E2E_FRONTEND_PORT=15180 bash scripts/e2e_acceptance.sh`
  - 结果：
    - Playwright 仍通过
    - 末尾 `Cancel running task(s)` 消失

### 2) 结论

问题并非主链路逻辑错误，而是 **收尾时序问题**：

- Playwright 结束后，脚本在执行 docs audit 前仍保持 frontend 存活；
- frontend 在这段窗口里持续轮询 `market health/world frame`；
- cleanup 执行 backend SIGTERM 时，残留请求仍在处理，导致 uvicorn 报 `Cancel running task(s)`。

## 收敛方案

在 `scripts/e2e_acceptance.sh` 做两点：

1. 增加显式 stop 函数（`stop_frontend` / `stop_backend`）与 `wait_pid_exit`，实现 `TERM -> wait -> KILL(兜底)`。
2. 在 `Playwright passed` 后、`docs audit` 前 **主动停止 FE/BE**，避免 docs audit 期间继续产生后端轮询请求。

关键改动位置：

- `scripts/e2e_acceptance.sh`
  - `wait_pid_exit`
  - `stop_frontend` / `stop_backend`
  - 在 `OK: Playwright E2E passed.` 后先 stop，再跑 docs audit

## 验收结果

执行：

- `E2E_BACKEND_PORT=18080 E2E_FRONTEND_PORT=15180 bash scripts/e2e_acceptance.sh`

输出：

- `12 passed`
- `OK: Playwright E2E passed.`
- 收尾阶段不再出现 `Cancel N running task(s)` 报错

对应日志：

- `output/e2e_acceptance_2026-02-11-backend-hardening-final-v6.log`

## 防回归建议

1. 保持 `Playwright -> stop FE/BE -> docs audit` 顺序，不要回退到“docs audit 后再 cleanup”。
2. 如需复查此类问题，优先做一次 `E2E_SKIP_DOC_AUDIT=1` 对照实验，先判断是“收尾时序”还是“业务逻辑”。
3. 若未来新增长轮询接口，优先检查收尾窗口是否仍会产生请求风暴。
