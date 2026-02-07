---
name: tc-market-kline-fastpath-v2
description: Use when implementing or refactoring market K-line fastpath v2 (freqtrade datadir bootstrap + batch SQLite upsert + pluggable realtime source) while preserving the existing HTTP/WS contracts.
metadata:
  short-description: market kline fastpath v2 工作流
---

# tc-market-kline-fastpath-v2（市场 K 线 Fastpath v2）

目标：把市场 K 线链路升级为 v2（历史复用 + 批量落库 + 可插拔实时源），同时保持对外契约稳定、可回滚、可验收。

## 何时使用（触发条件）

- 修改/新增任何会影响以下主链路的代码或行为：
  - `GET /api/market/candles`（历史/增量读取）
  - `WS /ws/market`（subscribe + `candle_closed` 推送）
  - ingest（ccxt 轮询 / Binance kline WS）
  - 历史 bootstrap（freqtrade datadir → SQLite）
- 相关实现常见落点：`backend/app/ingest_ccxt.py`、`backend/app/ingest_supervisor.py`、`backend/app/store.py`

## 关键不变量（硬约束）

- **只以 `closed candle` 作为权威输入**：forming 仅用于展示，不进因子/策略，不作为权威历史落库。
- **稳定主键**：`candle_id == "{series_id}:{candle_time}"`；所有去重/对齐都以 `series_id + candle_time` 为准。
- **写库必须批量化**：单批 `to_write` 使用单连接/单事务/单次 commit（避免逐根 connect/commit）。
- **幂等 + 单调输出**：重复 ingest 同一 `candle_id` 安全；对外输出按 `candle_time` 升序；遇到 gap 必须显式处理（HTTP 补齐或发 gap 信号）。
- **对外契约不破坏**：保持 `GetCandlesResponse` 与 WS 消息结构不变（最多做“向后兼容的字段增加”）。

## 工作流（按里程碑推进）

1) **以 plan 为唯一 SoT**：先对齐目标/开关/回滚口径：`docs/plan/2026-02-02-market-kline-fastpath-v2.md`
2) **开发前硬门禁：先写“主链路 E2E 用户故事 + 测试用例”**（用 `tc-e2e-gate` 模板）
   - 必须先在 plan 里写出 E2E 用户故事（包含“具体场景与具体数值”）。
   - 必须先准备好对应的 E2E 测试用例文件（允许先失败，但必须能跑起来并失败在正确位置）。
   - 例：用户打开 `BTC/USDT 4h` 图 → `GET /api/market/candles` 返回最后一根 `close=99999` → 触发一次 finalized 写入 → `WS /ws/market` 收到新 `candle_closed`，其 `open=10000` → UI 追加一根 candle。
2) **先 M0 再 M1/M2**（每步都可独立回滚）：
   - M0：ccxt ingest 批量 upsert + 单 commit
   - M1：freqtrade datadir bootstrap（必须有开关，默认可关闭）
   - M2：Binance kline WS finalized-only（必须可切回 ccxt 兜底）
3) **每步都补最小验证**：至少跑后端测试（见下方命令），必要时加/改对应测试用例。

## 交付声明（必须）

开发完成时，必须明确声明：
- 覆盖主链路的用户故事是哪一个（Story ID）
- 覆盖它的 E2E 测试用例是哪一个（test file path + test name）
- 用户操作流程是什么、触发了哪些接口、走了什么链路（handler → service → store/ws）
- 预期是什么、结果是什么（必须写具体数值，例如 candle_time/close/open/条数/排序），并指明证据来源（UI/HTTP/WS/SQL/trace）

## 验证命令（最小集合）

后端（离线、稳定、快速）：

```bash
python3 -m pytest backend/tests/test_market_candles.py -q
python3 -m pytest backend/tests/test_market_ws.py -q
python3 -m pytest backend/tests/test_ingest_ccxt_loop_mapping.py -q
python3 -m pytest backend/tests/test_history_bootstrapper.py -q
python3 -m pytest backend/tests/test_e2e_user_story_market_sync.py -q
```

前后端联调（可选，但推荐在合并前跑一次）：

```bash
bash scripts/e2e_acceptance.sh
```

## 交付证据（建议）

- 贴出你实际跑的命令 + 退出码为 0 的输出摘要。
- 若跑了 Playwright：附 `output/playwright/` 下 trace/screenshot/video 路径。
