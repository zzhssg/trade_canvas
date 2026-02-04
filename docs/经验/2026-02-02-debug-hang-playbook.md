---
title: 经验：后端卡住时的“证据优先”排查手册（SIGUSR1 + refcount + 超时）
status: done
created: 2026-02-02
updated: 2026-02-02
---

## 场景与目标

场景：后端偶发卡死、`Ctrl+C` 退出不干净、端口残留占用；以及图表出现异常（例如 1970 时间轴）。

目标：把排查流程标准化为“证据优先”，10 分钟内定位到：卡在子进程 / 卡在网络 / 卡在 WS ingest 泄漏 / 还是 DB 脏数据。

## 做对了什么（可复用动作）

1) **卡住先抓堆栈**（不靠猜）
- 开启：`TRADE_CANVAS_ENABLE_FAULTHANDLER=1`（`scripts/dev_backend.sh` 默认开启）
- 找 PID：`lsof -tiTCP:8000`
- Dump：`kill -USR1 <pid>`（打印 all threads traceback）

2) **用可观测的“状态快照”判断是否泄漏**
- 开启 debug：`TRADE_CANVAS_ENABLE_DEBUG_API=1`
- 看 ondemand ingest：`GET /api/market/debug/ingest_state`
  - 关注：`jobs` 数量是否持续增加、`refcount` 是否断开后仍不归零。

3) **外部依赖默认加超时**
- freqtrade 子进程：`TRADE_CANVAS_FREQTRADE_SUBPROCESS_TIMEOUT_S`（默认 120s）
- ccxt HTTP：`TRADE_CANVAS_CCXT_TIMEOUT_MS`（默认 10000ms）

4) **出现 1970 时间轴，先假设 DB 被污染**
- 直接清 DB 再启动：`bash scripts/dev_backend.sh --restart --fresh-db`
- 或仅清某个 series：`sqlite3 backend/data/market.db "delete from candles where series_id='...';"`

## 为什么有效（机制/约束）

- 堆栈是最短路径：能直接把“卡住在哪”变成可讨论的事实（线程池/网络/子进程/锁）。
- refcount + debug snapshot 把“泄漏”量化：避免把“越来越慢”误判成“某个算法慢”。
- 默认超时把“无限等待”变成“可恢复失败”，对开发和实盘都更安全。

## 复用方式（下次如何触发）

- 任何出现“卡住/退不掉/端口残留/越来越慢”时，按顺序做：
  1) `kill -USR1 <pid>` 抓堆栈
  2) `GET /api/market/debug/ingest_state` 看 job/refcount 是否异常
  3) 若涉及回测：确认子进程超时是否生效
  4) 若时间轴异常：先清 DB（`--fresh-db`）排除脏数据

## 关联

- `scripts/dev_backend.sh`
- `backend/app/main.py`
- `backend/app/freqtrade_runner.py`
- `backend/app/ingest_ccxt.py`

