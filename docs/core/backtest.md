---
title: backtest
status: draft
created: 2026-02-02
updated: 2026-02-02
---

# backtest

目标：在 trade_canvas 内提供一个“最小可用”的回测模块：
- **展示策略列表**（来自 freqtrade 的策略解析结果）
- **选择策略 + pair + timeframe 进行回测**
- **打印并回传 freqtrade backtesting 的输出**（stdout/stderr）

本设计“批判性继承”自 `trade_system`：只继承“边界契约 / 工程陷阱 / 可复现口径”，不继承其任务系统与复杂装配。

参考来源（仅对齐口径/陷阱）：
- `../trade_system/user_data/backend/app/services/backtest_service.py`（子进程调度思路）
- `../trade_system/user_data/doc/Core/Assets/pitfalls/2026-01-22_freqtrade-offline-static-markets-precisionmode.md`（离线回测 0 trades 陷阱）

---

## 1. SoT（真源）

- 回测 API + 参数口径：本文件
- 回测后端实现：`backend/app/main.py`
- 回测临时 config 生成：`backend/app/freqtrade_config.py`
- 子进程封装：`backend/app/freqtrade_runner.py`
- 前端页面：`frontend/src/pages/BacktestPage.tsx`

---

## 2. API 契约（最小 v1）

### 2.1 策略列表

`GET /api/backtest/strategies`

Response:
```json
{ "strategies": ["StrategyA", "StrategyB"] }
```

说明：
- 策略列表由 `freqtrade list-strategies --strategy-path ./Strategy` 的 stdout 解析得到（仅保留合法的 Python 标识符行）。
- 约束：回测只读取本项目 `./Strategy` 下的策略（不从 userdir/strategies 扫描）。

### 2.2 运行回测

`POST /api/backtest/run`

Request:
```json
{
  "strategy_name": "MyStrategy",
  "pair": "BTC/USDT",
  "timeframe": "1h",
  "timerange": "20260130-20260201"
}
```

Response:
```json
{
  "ok": true,
  "exit_code": 0,
  "duration_ms": 1234,
  "command": ["freqtrade","backtesting", "..."],
  "stdout": "...",
  "stderr": "..."
}
```

约束：
- `strategy_name` 必须是合法标识符，并且必须存在于 `list-strategies` 结果中。
- `pair/timeframe/timerange` 只作为 freqtrade CLI 参数透传（MVP 不做更深层校验）。
- 后端会 **打印** stdout/stderr（满足“打印回测结果”的需求），同时回传给前端展示。
- 若 `datadir` 中不存在对应 `pair+timeframe(+trading_mode)` 的 OHLCV 历史数据，后端会在运行前直接返回 `422`（`detail.message=no_ohlcv_history`），并给出 `expected_paths / available_timeframes / download_data_cmd` 作为可执行修复指引。

---

## 3. 运行时配置（环境变量）

后端（uvicorn 进程）读取：

- `TRADE_CANVAS_FREQTRADE_ROOT`
  - freqtrade 执行的工作目录（用于相对路径与 PYTHONPATH 注入）。
- `TRADE_CANVAS_FREQTRADE_CONFIG`
  - base config 路径（后端会基于它生成“最小回测临时 config”）。
- `TRADE_CANVAS_FREQTRADE_USERDIR`（可选）
  - 传给 freqtrade 的 `--userdir`；留空则不传（使用 freqtrade 默认 user_data 目录）。
- `TRADE_CANVAS_FREQTRADE_BIN`（可选，默认 `freqtrade`）
  - 子进程可执行文件名/路径。
- `TRADE_CANVAS_FREQTRADE_STRATEGY_PATH`（可选，默认 `./Strategy`）
  - 传给 freqtrade 的 `--strategy-path`，用于把策略放在项目内统一目录（不强制在 userdir/strategies 下）。
- `TRADE_CANVAS_FREQTRADE_OFFLINE_MARKETS`（可选，建议 dev 默认开启）
  - 值为 `1` 时，freqtrade 子进程会通过 `sitecustomize.py` 注入“最小 spot markets”，避免 backtesting 启动阶段访问交易所 `exchangeInfo`（适用于网络不可用/地区限制）。
- `TRADE_CANVAS_BACKTEST_REQUIRE_TRADES`（可选，建议 dev 默认开启）
  - 值为 `1` 时，回测成功必须满足 `total_trades > 0`，否则后端返回 `422 (no_trades)` 作为 fail-safe。

前端：
- `VITE_API_BASE`
  - 例如 `http://127.0.0.1:8000`（开发态跨端口调用后端）。

---

## 4. 关键工程点（批判性继承）

### 4.1 “可复现 > 方便”

- 回测调用必须使用 argv 数组（禁止 shell 字符串拼接），避免注入与转义坑。
- 默认将 pairlist 收敛为单 pair（避免“配置里巨大 whitelist 导致一键回测跑到天荒地老”）。
- 子进程会显式传 `--datadir <path>`（从 `TRADE_CANVAS_FREQTRADE_CONFIG` 解析并归一化为绝对路径），避免 freqtrade 默认把 datadir 解析到 userdir 下导致“预检与实际执行口径不一致”。

### 4.2 trade_system 的 `user_data.*` import 兼容

部分策略会 `import user_data...`，且 freqtrade 可能会在运行时更改 cwd / sys.path。

MVP 处理：
- 子进程强制注入 `PYTHONPATH += TRADE_CANVAS_FREQTRADE_ROOT`，确保 `user_data` 可被 import。

### 4.3 离线回测 0 trades 的静态 markets 精度陷阱

如果后续要支持离线对拍（不依赖交易所 exchangeInfo），需要特别注意：
- `exchange.offline_mode=true` + `exchange.static_markets` 的 `precision` 含义可能是 **tick size** 而非小数位。

当前 trade_canvas 不内置该能力，但已在设计中明确“坑位”，避免未来踩雷。

---

## 5. 非目标（MVP 不做）

- 回测任务队列/取消/WS log stream（trade_system 已有实现，但本仓暂不复刻）
- 解析回测产物（json/zip）并结构化展示（先把 stdout/stderr 打通）
- 自动 download-data / 数据缺失自动补齐（仍由用户自行准备 datadir）

---

## 6. E2E 用户故事用例（覆盖主链路）

- 市场 K 线同步主链路（HTTP ingest/read + WS catchup/live + gap）：`backend/tests/test_e2e_user_story_market_sync.py`
- 回测主链路（策略列表 + 运行回测 + 打印 stdout/stderr）：`backend/tests/test_backtest_api.py`
