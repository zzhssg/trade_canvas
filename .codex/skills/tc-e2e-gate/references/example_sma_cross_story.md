# 示例：trade_canvas SMA cross（E2E 用户故事）

用途：示例一个“从输入到策略信号”的最小 E2E 主流程如何写清楚、如何给证据。

## Persona / Goal

- Persona：量化开发者
- Goal：把 trade_canvas 的单一真源（CandleClosed→sqlite→kernel→ledger）接入 freqtrade，跑通回测/实盘策略加载与信号输出。

## Entry / Exit

- Entry：给定一段闭合 K 线 fixture（`fixtures/klines_mock_BTCUSDT_1m_60.jsonl`）作为输入。
- Exit：能在 DataFrame 上看到 `enter_long` 信号列，并且 `candle_id` 对齐且可重复（同输入同输出）。

## Preconditions

- Python 环境可运行 pytest（本仓库当前用 `pytest`）。
- 如果要直接跑 freqtrade：机器上已安装 `freqtrade`，并准备好 config（本仓库后端提供了 backtest runner，但本示例主要用 pytest 证据）。

## Main Flow（步骤 + 断言）

1) 把 CandleClosed 序列写入 sqlite store，并逐根调用 kernel 增量更新
   - Action：跑 `tests/test_e2e_sqlite_pipeline.py`
   - Assertions：
     - `ledger_latest.candle_id` 必须等于 `candles` 表里的最新 candle_id（对齐门禁）
     - rerun 到新 db 的输出必须一致（确定性）
   - Evidence：
     - 测试通过（退出码 0）

2) 将 kernel 产物桥接到 freqtrade DataFrame（strategy adapter）
   - Action：跑 `tests/test_freqtrade_adapter.py`
   - Assertions：
     - DataFrame 必须包含 `tc_*` 列（指标与信号）
     - 该 fixture 下 `tc_open_long` 至少出现一次（证明主链路有动作）
   - Evidence：
     - 测试通过（退出码 0）

3) 让 freqtrade 能发现并加载策略类（如果本机装了 freqtrade）
   - Action：
     - `export TRADE_CANVAS_FREQTRADE_USERDIR="$(pwd)/user_data_test"`
     - `freqtrade list-strategies --userdir "$TRADE_CANVAS_FREQTRADE_USERDIR" -1 --recursive-strategy-search`
   - Assertions：
     - 输出中包含 `TradeCanvasSmaCross`

## Produced Data

- sqlite db（策略侧运行期状态）：
  - 路径：由 `TRADE_CANVAS_STRATEGY_DB_PATH` 或默认 temp 路径决定
  - 表：
    - `candles`（输入）
    - `kernel_state`（增量状态）
    - `ledger_latest`（每 symbol/timeframe 最新 ledger）
    - `overlay_events`（可视化/信号标记）
  - 检查方式：
    - 直接用 sqlite client 查询，或在测试里断言读取结果

## Verification Commands（证据）

- `pytest -q`
  - 预期：全部通过；包含上述 2 条 E2E/adapter 测试

