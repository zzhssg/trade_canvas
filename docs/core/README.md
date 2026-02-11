---
title: Core 文档索引
status: done
created: 2026-02-02
updated: 2026-02-11
---

# Core 文档索引

`docs/core/` 是 trade_canvas 的架构真源目录，目标是保证“同输入同输出”的主链路可理解、可验收、可回滚。

## 优先阅读顺序（后端）

1. `docs/core/architecture.md`
   - 当前系统边界、模块职责、扩展策略。
2. `docs/core/backend-chain-breakdown.md`
   - 启动装配、写链路、实时链路、读链路、replay/backtest 的代码级拆解。
3. `docs/core/code-framework-and-core-chain.md`
   - 面向入门读者的代码框架地图 + 核心链路 + 重启后 K 线补齐说明。
4. `docs/core/market-kline-sync.md`
   - 市场数据同步口径（closed 权威、forming 展示、补齐/订阅策略）。
5. `docs/core/factor-modular-architecture.md`
   - 因子插件化写读链路、接入面与不变量。
6. `docs/core/backtest.md`
   - backtest/freqtrade 适配边界与 fail-safe。

## 契约与接口

- API 文档（v1）：`docs/core/api/v1/README.md`
- 契约目录：`docs/core/contracts/README.md`
- 真源总表：`docs/core/source-of-truth.md`

## 协作与门禁

- Agent 工作流：`docs/core/agent-workflow.md`
- 文档状态约定：`docs/core/doc-status.md`
- 项目 skills：`docs/core/skills.md`

## 其他专题

- trade_oracle（独立研究项目）：`docs/core/trade-oracle.md`
