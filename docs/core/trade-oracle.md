---
title: trade_oracle（独立研究项目）
status: draft
created: 2026-02-09
updated: 2026-02-09
---

# trade_oracle

trade_oracle 是独立于 trade_canvas 的研究项目：

- K 线数据来源：只消费 trade_canvas API（不直连 trade_canvas DB）
- 研究目标：基于资产出生八字 + 流年/月/日，做可复现的涨跌分析
- 首期 MVP：基于当前时间与 BTC 日线，输出一份分析报告（Markdown + JSON 证据）

## 快速开始

```bash
python3 -m pip install -r trade_oracle/requirements.txt
python3 -m trade_oracle.cli \
  --series-id binance:futures:BTC/USDT:1d \
  --output-dir trade_oracle/output
```

默认读取环境变量：

- `TRADE_ORACLE_MARKET_API_BASE`（默认 `http://127.0.0.1:8000`）
- `TRADE_ORACLE_ENABLE_SX_CROSSCHECK`（默认 `0`）
- `TRADE_ORACLE_ENABLE_STRATEGY_SEARCH`（默认 `0`）
- `TRADE_ORACLE_ENABLE_BACKTEST`（默认 `0`）
- `TRADE_ORACLE_WF_TRAIN_SIZE`（默认 `90`）
- `TRADE_ORACLE_WF_TEST_SIZE`（默认 `30`）
- `TRADE_ORACLE_TRADE_FEE_RATE`（默认 `0.0008`）
- `TRADE_ORACLE_TARGET_WIN_RATE`（默认 `0.5`）
- `TRADE_ORACLE_TARGET_REWARD_RISK`（默认 `2.0`）
- `TRADE_ORACLE_ENABLE_TRUE_SOLAR_TIME`（默认 `1`，开启真太阳时换算）
- `TRADE_ORACLE_SOLAR_LONGITUDE_DEG`（默认 `24.9384`，赫尔辛基经度）
- `TRADE_ORACLE_SOLAR_TZ_OFFSET_HOURS`（默认 `2.0`，按 GMT+2 标准时区换算）
- `TRADE_ORACLE_STRICT_CALENDAR_LIB`（默认 `1`，缺少历法库时直接报错，不降级伪历法）

## CLI 任务

```bash
# 当前时点分析（输出 report.md + evidence.json）
python3 -m trade_oracle.cli --task analyze

# 基于 trade_canvas API 的 walk-forward 回测（输出 backtest_evidence.json）
TRADE_ORACLE_ENABLE_BACKTEST=1 python3 -m trade_oracle.cli --task backtest-live

# 历法双引擎差异审计（默认 2009-01-03 到 2026-01-01，步长 30 天，样本 > 100）
python3 -m trade_oracle.cli --task calendar-audit
```

## BTC 基准时间约定

- 当前默认基准：`2009-01-03 18:15 GMT+2`。
- 系统先换算为 UTC `2009-01-03T16:15:00Z`，再按真太阳时（赫尔辛基经度 24.9384E）计算干支。
- 该约定下 BTC 原局四柱为：`戊子 甲子 戊申 辛酉`。

## API（MVP）

```bash
uvicorn trade_oracle.apps.api.main:app --reload --port 8091
```

- `GET /api/oracle/analyze/current?series_id=binance:futures:BTC/USDT:1d`
- `GET /api/oracle/backtest/run?series_id=binance:futures:BTC/USDT:1d`

## 与 trade_canvas 前端集成

- 入口位置：右上角导航，`Live` 右侧 `Oracle`。
- 开关：`VITE_ENABLE_TRADE_ORACLE_PAGE`（默认 `1`）。
- API base：`VITE_ORACLE_API_BASE_URL`（dev 默认 `/oracle-api`，由 Vite 代理到 `http://127.0.0.1:8091`）。


## Troubleshooting

- Oracle 页面显示 `oracle_api_unreachable`：先启动 `trade_oracle` API（`uvicorn trade_oracle.apps.api.main:app --reload --port 8091`）。
- Oracle API 返回 `market_source_unavailable`（HTTP 503）：说明 `trade_oracle` 已启动，但 `trade_canvas` 市场后端不可访问，请先启动 `bash scripts/dev_backend.sh`。
