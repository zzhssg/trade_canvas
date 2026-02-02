---
title: 用 candle_id 对齐策略与绘图的最小 E2E
status: done
---

# 用 candle_id 对齐策略与绘图的最小 E2E

## 场景与目标

我们要验证一个关键不变量：策略开仓信号与图表绘图标记必须同源（同一份 closed candle 输入、同一 `candle_id`）。

目标是先把主链路“闭环可验收”跑通，再把 SMA 占位因子替换为 pivot/笔/锚等复杂拓扑。

## 做对了什么（可复用动作）

- 用固定 fixture 作为真源输入（可复现）：`fixtures/klines_mock_BTCUSDT_1m_60.jsonl`
- 内核只吃 `CandleClosed`，每根增量更新并落库：`trade_canvas/kernel.py`
- 分层落库最小化（candles / kernel_state / ledger_latest / overlay_events）：`trade_canvas/store.py`
- 单适配器只读落库产物，并强制 `candle_id` 对齐，不一致直接 fail-safe：`trade_canvas/adapter.py`
- E2E 同时包含：
  - happy path（链路跑通、最新 candle 对齐）
  - 负例（人为制造不同步，必须拒绝）：`tests/test_e2e_sqlite_pipeline.py`

## 为什么有效

- 把“同源一致性”变成可测试的硬约束：`candle_id` 既是对齐键，也是 fail-safe 门槛。
- 适配器只读落库产物，避免“策略侧重算 / 图表侧重算”导致的语义漂移。
- 负例能确保：一旦数据不同步，系统宁可不交易也不乱交易。

## 复用方式（下次如何触发）

当你新增/调整任意一个环节（落库 schema、因子输出结构、adapter 投影规则）时：
- 先跑 `python3 -m unittest discover -s tests -p "test_*.py"`
- 需要联调时再跑 `bash scripts/e2e_acceptance.sh`

## 关联

- 代码：
  - `trade_canvas/types.py`
  - `trade_canvas/store.py`
  - `trade_canvas/kernel.py`
  - `trade_canvas/adapter.py`
  - `tests/test_e2e_sqlite_pipeline.py`
- 命令：
  - `python3 -m unittest discover -s tests -p "test_*.py"`
