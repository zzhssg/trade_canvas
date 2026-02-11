---
title: Backtest 架构与契约
status: done
created: 2026-02-02
updated: 2026-02-11
---

# Backtest 架构与契约

目标：在 trade_canvas 内提供可复现、可排障、可扩展的回测主链路。

---

## 1. 当前后端分层

- 路由：`backend/app/backtest_routes.py`
  - 暴露 HTTP API，不承载业务细节。
- 服务：`backend/app/backtest_service.py`
  - 负责参数校验、数据可用性检查、freqtrade 调用编排。
- 运行时执行：
  - `backend/app/backtest_runtime.py`
  - `backend/app/freqtrade_runner.py`
  - `backend/app/freqtrade_config.py`
  - `backend/app/freqtrade_data.py`

DI 装配入口：`backend/app/container.py`。

---

## 2. API 契约（v1）

### 2.1 获取策略列表

`GET /api/backtest/strategies`

返回：
- `strategies: string[]`

语义：
- mock 模式下固定返回 `DemoStrategy`。
- 真实模式下从 strategy path 解析策略。

### 2.2 获取交易对可用周期

`GET /api/backtest/pair_timeframes?pair=BTC/USDT`

返回：
- `pair`
- `trading_mode`
- `datadir`
- `available_timeframes`

语义：
- 用于前端提前发现数据缺失，避免直接触发失败回测。

### 2.3 运行回测

`POST /api/backtest/run`

请求字段：
- `strategy_name`
- `pair`
- `timeframe`
- `timerange`

返回字段：
- `ok` / `exit_code` / `duration_ms`
- `command`
- `stdout` / `stderr`

失败语义（关键）：
- `422 backtest.history_missing`：datadir 缺失目标数据。
- `422 backtest.no_trades`：要求必须有成交且结果为 0。
- `500 backtest.*`：freqtrade 执行或配置异常。

---

## 3. 配置与开关

### 3.1 Settings（`config.py`）

- `TRADE_CANVAS_FREQTRADE_ROOT`
- `TRADE_CANVAS_FREQTRADE_CONFIG`
- `TRADE_CANVAS_FREQTRADE_USERDIR`
- `TRADE_CANVAS_FREQTRADE_BIN`
- `TRADE_CANVAS_FREQTRADE_STRATEGY_PATH`

### 3.2 RuntimeFlags（`runtime_flags.py`）

- `TRADE_CANVAS_BACKTEST_REQUIRE_TRADES`
- `TRADE_CANVAS_FREQTRADE_MOCK`

语义：
- `require_trades=1`：无成交视为失败（用于门禁场景）。
- `freqtrade_mock=1`：启用联调 mock，不依赖真实 freqtrade 环境。

---

## 4. 关键工程约束

1. 子进程调用必须使用 argv 数组，禁止 shell 拼接。
2. datadir 可用性必须在执行前校验，失败要返回可执行修复提示。
3. 回测日志（stdout/stderr）必须可回传与可追踪。
4. 策略名必须经过白名单式校验，避免注入和误执行。

---

## 5. 与因子主链路的关系

- `freqtrade_adapter_v1.py` 负责将因子 ledger 映射到 `tc_*` 信号列。
- backtest API 本身不直接实现因子逻辑，只消费 adapter 输出。
- factor 配置变更应通过 runtime flags/契约同步，避免回测口径漂移。

---

## 6. 验收命令

```bash
pytest -q
```

若同步修改 core 文档：

```bash
bash docs/scripts/doc_audit.sh
```

---

## 7. 已过期口径

- “backtest 后端实现在 `main.py`”：已过期，当前为 routes + service 分层。
- “MVP 只支持策略列表与 run”：已过期，当前已提供 `pair_timeframes` 预检入口。
