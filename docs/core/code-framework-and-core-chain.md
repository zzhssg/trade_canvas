---
title: 代码框架与核心链路（快速入门）
status: done
created: 2026-02-11
updated: 2026-02-11
---

# 代码框架与核心链路（快速入门）

适用对象：第一次接手 `trade_canvas` 后端的开发者。  
目标：10 分钟内建立“入口 -> 主链路 -> 排障路径”的心智模型。

---

## 1. 三条必须记住的原则

1. `closed candle` 是权威输入，驱动 factor/overlay/strategy。
2. `forming candle` 只用于展示，不落库、不进因子。
3. 写链路始终走单路径：`store -> factor -> overlay -> publish`。

---

## 2. 先看哪几个文件

1. 装配入口：`backend/app/main.py`
2. 容器依赖：`backend/app/container.py`
3. 市场运行时：`backend/app/market_runtime_builder.py`
4. 写链路核心：`backend/app/pipelines/ingest_pipeline.py`
5. 世界态读链路：`backend/app/read_models/world_read_service.py`

---

## 3. 模块职责（一句话版）

- `market_http_routes.py` / `market_ws_routes.py`：协议入口（参数与错误语义）。
- `market_ingest_service.py`：市场写请求编排。
- `ingest_supervisor.py`：实时任务生命周期（whitelist/ondemand）。
- `factor_orchestrator.py`：因子增量推进。
- `overlay_orchestrator.py`：绘图增量推进。
- `read_models/*`：factor/draw/world 的统一读取与对齐门禁。

---

## 4. 重启后的 K 线补齐口径

当前实现是“按需补齐”，不是“启动即全量补齐”。

触发点：
1. `/api/market/candles` 读路径（可选 auto tail backfill）。
2. WS 订阅 catchup 或 gap 处理。
3. 任务启动时的历史导入（取决于运行时配置）。

实操建议：
1. 看 `/api/market/health` 或 debug 接口确认 lag。
2. 触发一次 candles 读取。
3. 再次确认 `missing_candles` 是否下降。

---

## 5. 常见排障顺序

1. 先看 route（是否参数/协议错误）。
2. 再看 service（是否分支走偏）。
3. 再看 pipeline/orchestrator（是否 step 失败）。
4. 最后看 flags（是否开关或阈值配置错误）。

---

## 6. 深入阅读入口

- 架构全景：`docs/core/architecture.md`
- 代码级链路拆解：`docs/core/backend-chain-breakdown.md`
- 市场同步细节：`docs/core/market-kline-sync.md`
- 因子模块化：`docs/core/factor-modular-architecture.md`
- 回测链路：`docs/core/backtest.md`
