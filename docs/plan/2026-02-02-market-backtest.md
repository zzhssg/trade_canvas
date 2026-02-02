---
title: 市场回测模块（freqtrade bridge）
status: 草稿
owner:
created: 2026-02-02
updated: 2026-02-02
---

## 背景

trade_canvas 需要一条“可验收”的回测链路，用于：
- 快速验证策略/参数在指定市场数据上的表现
- 与未来的因子引擎/ledger/replay 做一致性对拍（后续迭代）

首期优先目标：把 freqtrade backtesting 当作权威执行器，先打通 UI → 后端 → 子进程 → 输出展示。

契约真源见：`docs/core/backtest.md`。

## 目标 / 非目标

### 目标（Do）

- 展示策略列表（freqtrade list-strategies）
- 选择策略 + pair + timeframe + timerange 运行 backtesting
- 打印回测结果（stdout/stderr）并在前端展示

### 非目标（Don’t / MVP 不做）

- 回测任务队列、取消、日志 WS 流（后续可按需“批判性继承” trade_system）
- 结果文件解析与可视化对比（先打通文本输出）
- 自动下载数据（数据准备先交给用户 / 现有脚手架）

## 方案概述

三层拆分（小而清晰）：

1) `freqtrade_config`：基于 base config 生成“最小回测临时 config”（强制单 pair，补齐必需字段）
2) `freqtrade_runner`：统一 subprocess 调度（argv 方式；注入 PYTHONPATH 兼容 `user_data.*`）
3) `backtest API + UI`：API 返回 stdout/stderr；前端呈现与复制

## 里程碑

- M0：定义 SoT（本 plan + core doc）
- M1：后端 API：`/api/backtest/strategies` + `/api/backtest/run`
- M2：前端页面：策略选择 + 运行 + 输出展示
- M3：补充测试（mock subprocess）与 runbook（环境变量/启动方式）

## 验收标准

- 打开 Backtest 页面能看到策略列表
- 选择策略后点击 Run，能看到 backtesting 输出（即使 0 trades 也算通过）
- 后端日志中能看到 stdout/stderr 被打印（满足“打印回测结果”）

## 变更记录

- 2026-02-02: 创建（草稿）
