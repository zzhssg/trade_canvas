---
title: Core Contracts（契约索引）
status: done
created: 2026-02-02
updated: 2026-02-14
---

# Core Contracts（契约索引）

本目录存放后端主链路的协议/数据结构真源，目标是保证：
- 可实现（能直接映射到代码与 schema）；
- 可验收（能被 API/E2E 门禁验证）；
- 可演进（版本化升级且可回放）。

## 当前生效（v1）

- 因子外壳：`docs/core/contracts/factor_v1.md`
- 因子拓扑：`docs/core/contracts/factor_graph_v1.md`
- 因子插件：`docs/core/contracts/factor_plugin_v1.md`
- 因子 SDK：`docs/core/contracts/factor_sdk_v1.md`
- 因子账本：`docs/core/contracts/factor_ledger_v1.md`
- 二级增量账本：`docs/core/contracts/delta_ledger_v1.md`
- 绘图增量：`docs/core/contracts/draw_delta_v1.md`
- 中枢：`docs/core/contracts/zhongshu_v1.md`
- 锚：`docs/core/contracts/anchor_v1.md`
- 世界态 frame：`docs/core/contracts/world_state_v1.md`
- 世界态 delta：`docs/core/contracts/world_delta_v1.md`
- 回放帧：`docs/core/contracts/replay_frame_v1.md`
- 回放包：`docs/core/contracts/replay_package_v1.md`
- 策略消费边界：`docs/core/contracts/strategy_v1.md`
- 市场榜单：`docs/core/contracts/market_list_v1.md`

## 维护规则

1. 变更契约字段时，必须同步更新对应 API 文档（`docs/core/api/v1/`）。
2. 引入新高风险行为时，必须提供 `TRADE_CANVAS_ENABLE_*` 开关作为 kill-switch。
3. 发生 `feat/fix/refactor` 且影响核心契约时，必须跑 `bash docs/scripts/doc_audit.sh` 并提交证据。
