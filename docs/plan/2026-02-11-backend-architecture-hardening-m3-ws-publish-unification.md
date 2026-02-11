---
title: backend architecture hardening m3 ws publish unification
status: 待验收
owner: codex
created: 2026-02-11
updated: 2026-02-11
---

## 背景

- 当前 Binance WS flush 在 `ingest_binance_ws.py` 内手工发布 `closed_batch + factor.rebuild`，而 HTTP 写链路走 `IngestPipeline.publish`。
- 两条发布路径存在实现重复与行为漂移风险（后续改 message/异常策略时容易漏改）。
- 该改动触达实时主链路（高风险），需要 kill-switch 灰度上线。

## 目标 / 非目标

### 目标
- M3：把 WS 发布编排收敛到 `IngestPipeline.publish`（单点语义），并保留 legacy 回退开关。
- 发布异常策略可配置：WS 场景支持 `best_effort`，避免单个订阅异常放大为 ingest 断流。
- runtime/container/supervisor 贯通开关注入，保证可观测与可回滚。

### 非目标
- 不修改 WS 协议字段与消息类型。
- 不修改 forming 节流/derived 归并算法。
- 不调整 HTTP 写链路行为（仍保持严格 publish 失败即报错）。

## 方案概述

1. `IngestPipeline.publish` 新增 `best_effort` 参数，并复用到 `publish_system_rebuilds`。
2. `ingest_binance_ws` 增加 `_publish_pipeline_result_from_ws`：
   - 开关关闭：保持 legacy 手工发布语义；
   - 开关开启：调用 `ingest_pipeline.publish(result, best_effort=True)`。
3. 新增 runtime flag：
   - env：`TRADE_CANVAS_ENABLE_INGEST_WS_PIPELINE_PUBLISH`
   - 默认：`0`（关闭）
4. 注入链路：`RuntimeFlags -> market_runtime_builder -> IngestSupervisor -> run_binance_ws_ingest_loop`。
5. 测试覆盖：
   - pipeline `best_effort` 继续后续发布；
   - WS helper 在开关两态下走不同路径；
   - backend 容器 wiring 校验开关注入 supervisor。

## 里程碑

- M3A：发布器能力统一（pipeline best_effort）
- M3B：WS 路径 kill-switch 接入
- M3C：回归测试 + 文档更新 + 门禁验证

## 任务拆解
- [x] 新增 `TRADE_CANVAS_ENABLE_INGEST_WS_PIPELINE_PUBLISH` 并注入 `IngestSupervisor`
- [x] 改造 `IngestPipeline.publish/publish_system_rebuilds` 支持 `best_effort`
- [x] 改造 `ingest_binance_ws`，通过 helper 切换 legacy / pipeline 发布路径
- [x] 补齐测试（pipeline/ingest_binance_ws/runtime wiring）
- [x] 运行门禁并推进计划状态到待验收

## 风险与回滚

风险：
- 开关开启后，WS 发布顺序由 legacy “base-first”改为 pipeline “series_id 排序”；可能影响极少数依赖跨 series 顺序的隐式消费者。
- pipeline 发布异常策略切换若实现不当，可能导致 WS loop 误中断。

回滚：
- 运行时回滚：`TRADE_CANVAS_ENABLE_INGEST_WS_PIPELINE_PUBLISH=0`。
- 代码回滚：`git revert <m3-commit-sha>`（建议与 M1/M2 分开提交）。

## 验收标准

- `pytest -q backend/tests/test_ingest_pipeline.py backend/tests/test_ingest_binance_ws.py backend/tests/test_runtime_flags.py backend/tests/test_backend_architecture_flags.py`
- `pytest -q`
- `python3 -m mypy backend/app/pipelines/ingest_pipeline.py backend/app/ingest_binance_ws.py backend/app/ingest_supervisor.py backend/app/market_runtime_builder.py backend/app/runtime_flags.py`
- `bash docs/scripts/doc_audit.sh`

## E2E 用户故事（门禁）

- 角色：实时订阅用户
- 目标：在不改变 WS 协议的前提下，让 closed/system 发布语义由单点编排统一且可灰度回滚。
- 场景（具体数值）：
  1) `series_id=binance:futures:BTC/USDT:1m`，推送 closed `1700000000/1700000060`；
  2) 产生 derived `5m` 聚合以及 `factor.rebuild` 系统事件；
  3) 分别在开关 `0/1` 下执行 flush。
- 断言：
  - 开关=0：走 legacy 发布路径（helper 不调用 `ingest_pipeline.publish`）。
  - 开关=1：走 `ingest_pipeline.publish(best_effort=True)`。
  - 两种模式下均不会改变 WS payload schema（`candles_batch` + `system`）。

## 变更记录
- 2026-02-11: 创建（草稿）
- 2026-02-11: 绑定当前 worktree，并置为开发中。
- 2026-02-11: 完成 M3A/M3B/M3C，门禁通过（pytest/mypy/doc_audit）。
- 2026-02-11: 本地灰度验证 `TRADE_CANVAS_ENABLE_INGEST_WS_PIPELINE_PUBLISH=1`，`bash scripts/e2e_acceptance.sh` 通过（`12 passed`）。
