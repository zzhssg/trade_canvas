---
title: Factor 完全插件化（Phase H：Overlay 归桶声明 + Freqtrade Signal 插件）
status: 待验收
owner: codex
created: 2026-02-10
updated: 2026-02-10
---

## 背景

Phase G 后，主链路写路径与读路径已插件化，但仍有两处“新增 factor 需要改 orchestrator 主流程”的耦合点：
- `overlay_orchestrator.py` 仍内联 `pivot/pen/zhongshu/anchor` 事件归桶分支。
- `freqtrade_adapter_v1.py` 仍内联 `pen.confirmed` 信号打标分支。

## 目标 / 非目标

目标：
- 让 overlay ingest 的事件归桶来自 renderer plugin 声明（`bucket_specs`），新增绘图输入不再改 orchestrator 分支。
- 让 freqtrade ledger 注解的信号列来自 signal plugin 声明，新增策略信号不再改 adapter 主流程。
- 保持现有默认行为（`pen` 信号列语义）不变。

非目标：
- 不改 HTTP/WS 协议，不改前端渲染协议，不调整既有交易信号语义。

## 方案概述

1) Overlay：在 `overlay_renderer_plugins.py` 增加 `OverlayEventBucketSpec`、归桶配置构建器与归桶收集器；`OverlayOrchestrator` 仅调度插件与写库。
2) Freqtrade：新增 `freqtrade_signal_plugin_contract.py` 与 `freqtrade_signal_plugins.py`；`annotate_factor_ledger()` 改为“runtime 装配 + 归桶 + 插件 apply”。
3) 测试与文档同步：补插件归桶冲突/排序测试、freqtrade 自定义信号插件测试，并更新 core 架构与契约文档。

## 验收标准

- `pytest -q --collect-only`
- `pytest -q backend/tests/test_overlay_renderer_plugins.py backend/tests/test_freqtrade_adapter_v1.py`
- `pytest -q`
- `bash docs/scripts/doc_audit.sh`

## E2E 用户故事（门禁）

- Persona：策略开发者。
- 入口：向 `annotate_factor_ledger()` 输入一段 OHLCV dataframe（含可产生 pivot/pen 的价格序列）。
- 主链路：写入 candle → factor ingest → signal plugin 归桶消费 factor events → dataframe 信号列打标。
- 出口断言：
  - 默认信号插件产出 `tc_pen_confirmed/tc_enter_long/tc_enter_short`；
  - 注入自定义 signal plugin 时，无需修改 adapter 代码即可新增列并打标；
  - overlay 默认插件在归桶声明驱动下仍可产出 marker/polyline。
- 证据：`test_freqtrade_adapter_v1.py` + `test_overlay_renderer_plugins.py` 通过日志。

## 回滚

- 单提交回滚：`git revert <sha>`
- 最小文件回退：
  - `/Users/rick/code/trade_canvas/backend/app/overlay_renderer_plugins.py`
  - `/Users/rick/code/trade_canvas/backend/app/overlay_orchestrator.py`
  - `/Users/rick/code/trade_canvas/backend/app/freqtrade_adapter_v1.py`
  - `/Users/rick/code/trade_canvas/backend/app/freqtrade_signal_plugin_contract.py`
  - `/Users/rick/code/trade_canvas/backend/app/freqtrade_signal_plugins.py`
