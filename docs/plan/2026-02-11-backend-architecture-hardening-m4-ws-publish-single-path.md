---
title: backend architecture hardening m4 ws publish single path
status: 待验收
owner: codex
created: 2026-02-11
updated: 2026-02-11
---

## 背景

- M3 已引入 `TRADE_CANVAS_ENABLE_INGEST_WS_PIPELINE_PUBLISH`，但 `ingest_binance_ws.py` 仍保留一份手工发布逻辑（base/derived/system）。
- 当前是“开关分流 + 双实现并存”，后续维护仍存在漂移风险。
- 目标是把 WS 发布职责进一步收口到 `IngestPipeline`，让 WS 层只负责 ingest/flush，不再拼发布细节。

## 目标 / 非目标

### 目标
- 在不改变外部 WS 协议与开关语义前提下，移除 `ingest_binance_ws.py` 的手工发布分支。
- `IngestPipeline` 提供统一 WS 发布入口，承载两种语义：
  - unified 模式：全量 `best_effort`
  - legacy 兼容模式：primary strict + secondary/system best_effort
- 保持 `TRADE_CANVAS_ENABLE_INGEST_WS_PIPELINE_PUBLISH` 作为 kill-switch（默认 `0`）。

### 非目标
- 不调整 forming 广播节流参数与 derived 聚合算法。
- 不修改 `ws_market` 协议字段或消息类型。
- 不在本轮把开关默认值改为 `1`。

## 方案概述

1. `IngestPipeline` 新增 `publish_ws(...)`，统一承载 WS 发布策略。
2. `ingest_binance_ws._publish_pipeline_result_from_ws` 只做参数透传到 `IngestPipeline.publish_ws`，删除手工 `hub.publish_*` 分支。
3. 复用 `_publish_series_batch` 消除 `publish` / `publish_ws` 重复 batch 发送代码。
4. 补充测试覆盖：
   - `publish_ws` 两种模式语义；
   - WS helper 确认开关参数透传；
   - 现有 runtime/container wiring 维持兼容。

## 里程碑

- M4A：`IngestPipeline` 增加 WS 发布统一入口
- M4B：`ingest_binance_ws` 删除手工发布细节
- M4C：测试/文档门禁

## 任务拆解
- [x] 在 pipeline 中新增 `publish_ws` 并抽取批量发送共用逻辑
- [x] WS helper 统一委托 pipeline，移除直接 hub 发布分支
- [x] 补齐 publish_ws 行为测试与 helper 透传测试
- [x] 运行门禁并推进状态到待验收

## 风险与回滚

- 风险：legacy 兼容语义若实现偏差，可能影响 base/derived publish 错误处理边界。
- 回滚：
  - 运行时：`TRADE_CANVAS_ENABLE_INGEST_WS_PIPELINE_PUBLISH=0`（仍走 legacy 兼容策略）。
  - 代码：`git revert <m4-commit-sha>`。

## 验收标准

- `pytest -q backend/tests/test_ingest_pipeline.py backend/tests/test_ingest_binance_ws.py backend/tests/test_runtime_flags.py backend/tests/test_backend_architecture_flags.py`
- `pytest -q`
- `python3 -m mypy backend/app/pipelines/ingest_pipeline.py backend/app/ingest_binance_ws.py`
- `TRADE_CANVAS_ENABLE_INGEST_WS_PIPELINE_PUBLISH=1 bash scripts/e2e_acceptance.sh`
- `bash docs/scripts/doc_audit.sh`

## E2E 用户故事（门禁）

- 角色：实时订阅用户
- 目标：在 WS ingest flush 时，发布链路由 pipeline 单点编排且可通过开关切换语义。
- 场景（具体数值）：
  - `series_id=binance:futures:BTC/USDT:1m`
  - 连续 closed：`1700000000`、`1700000060`
  - 同步产生 derived 与 system 事件
- 断言：
  - 开关 `0/1` 下，WS 协议 schema 保持一致（`candles_batch` + `system`）。
  - `ingest_binance_ws` 不再直接依赖 `hub.publish_closed_batch/publish_system` 细节。
  - pipeline 发布错误策略符合 legacy/unified 两种预期。

## 变更记录
- 2026-02-11: 创建（草稿）
- 2026-02-11: 绑定 worktree 并进入开发中。
- 2026-02-11: 完成 M4A/M4B 代码改造，`pytest -q backend/tests/test_ingest_pipeline.py backend/tests/test_ingest_binance_ws.py` 通过。
- 2026-02-11: 完成 M4C 门禁（`pytest -q` / `mypy` / `TRADE_CANVAS_ENABLE_INGEST_WS_PIPELINE_PUBLISH=1 bash scripts/e2e_acceptance.sh` / `doc_audit`）。
