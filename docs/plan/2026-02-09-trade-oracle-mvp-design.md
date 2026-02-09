---
title: trade_oracle MVP（BTC 八字走势报告）
status: 开发中
owner: Codex
created: 2026-02-09
updated: 2026-02-09
---

## 背景

新建独立项目 `trade_oracle`，只复用 `trade_canvas` 的 K 线真源读取能力（API），其余分析链路独立。首期目标是：

- 使用 BTC 出生时间（2009-01-03 18:15:05 UTC）作为原局
- 用当前 UTC 时间计算流年/流月/流日
- 结合 BTC 日线 K 线，产出一份可复现的分析报告（Markdown + JSON 证据）

## 目标 / 非目标

### 目标

1. 形成可复现分析闭环：输入固定、输出可重复。
2. 历法转换具备双引擎口径（主引擎 + 抽样交叉校验）。
3. 形成盲派/格局派/旺衰派三套可计算评分。
4. 输出当前时点 BTC 报告，附带历史依据摘要。

### 非目标

1. 首期不承诺“稳定达到胜率 >50%、盈亏比 >2”。
2. 首期不做前端页面与实时流式分析。
3. 首期不支持多资产并行研究（先 BTC）。

## 方案概述

- 仓库结构：在当前仓内新增 `trade_oracle/` 目录，作为独立工程骨架。
- 数据输入：仅调用 `trade_canvas` 的 `GET /api/market/candles`。
- 历法模块：`lunar-python` 为主，`sxtwl` 抽样校验；缺失依赖时 fallback 并显式打标。
- 分析模块：三流派独立打分，输出总分、方向、置信度。
- 回测模块：保留 kill-switch，MVP 仅提供基础统计框架。
- 报告模块：生成 `report.md` 与 `evidence.json`。

## 里程碑

1. M0（本次）：项目骨架 + 分析闭环 + 报告输出。
2. M1：walk-forward 回测策略搜索与参数冻结。
3. M2：多资产扩展（ETH 等）与策略稳健性对拍。

## 任务拆解

- [x] 新增 `trade_oracle` 目录结构与基础契约文件。
- [x] 新增历法服务、资产注册、三流派评分、分析编排、报告渲染。
- [x] 新增 CLI 与 API 当前分析入口。
- [x] 新增最小测试（分析输出 + walk-forward 窗口）。
- [x] 接入真实 `lunar-python/sxtwl` 依赖声明（`requirements.txt` + 运行口径）。
- [x] 回测从单阈值升级为 walk-forward 阈值搜索（可由环境变量调参）。
- [x] 新增历法双引擎差异审计任务（固定样本 >100，落盘证据文件）。
- [x] 新增 market walk-forward 回测门槛证据输出（胜率/盈亏比目标与通过标记）。
- [x] 新增 trade_canvas 前端独立页面入口（TopBar: Live 右侧 Oracle）。
- [ ] 用真实 market API 样本补充“跨历法差异对拍”回归测试基准文件（M1）。

## 风险与回滚

### 风险

1. 历法库口径差异导致干支不一致。
2. 上游 K 线数据缺口导致结论漂移。
3. 规则打分过拟合历史样本。

### 回滚

1. 关闭 `TRADE_ORACLE_ENABLE_SX_CROSSCHECK`，仅保留主历法。
2. 关闭 `TRADE_ORACLE_ENABLE_BACKTEST`，保留纯分析报告。
3. 变更可通过单一 commit 回滚，不影响 `trade_canvas` 主链路。

## 验收标准

1. 命令 `python3 -m trade_oracle.cli --series-id binance:futures:BTC/USDT:1d` 能产出：
   - `trade_oracle/output/report.md`
   - `trade_oracle/output/evidence.json`
2. `pytest -q` 通过，包含新增 `tests/trade_oracle/*`。
3. 同一份 fixture 输入重复运行，关键证据字段可重复（分数与方向一致）。

## E2E 用户故事（门禁）

- Persona：量化研究员
- Goal：在当前时间生成 BTC 八字走势报告
- 入口：`trade_oracle.cli`（series_id=`binance:futures:BTC/USDT:1d`）
- 出口：`report.md + evidence.json`

流程断言：
1. 从 trade_canvas API 拉取日线历史（断言 `candles.count > 0`）。
2. 读取 BTC 出生时间并计算原局（断言 `birth_bazi` 四柱存在）。
3. 计算当前流时三流派分数（断言 `factor_scores` 长度=3）。
4. 输出综合方向与置信度（断言 `bias in bullish/bearish/neutral`）。
5. 报告落盘（断言文件存在且包含“免责声明”）。

反例：
- 当 API 返回空 candles 时，流程应失败并提示 `analysis_failed`。

## 变更记录

- 2026-02-09: 创建并进入开发中。
