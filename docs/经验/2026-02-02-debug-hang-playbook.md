---
title: "后端卡死/1970 K 线排查手册（证据优先 + 超时 + DB 清理）"
status: done
created: 2026-02-02
updated: 2026-02-09
---

# 后端卡死/1970 K 线排查手册（证据优先 + 超时 + DB 清理）

## 问题背景

联调中反复出现两类高频问题：

1. **后端卡死/退不掉**：后端跑一段时间"卡住"，`Ctrl+C` 也不退出，端口残留占用（`scripts/dev_backend.sh` 报 port already in use）。触发条件通常包括：开启图表 WS、跑回测、或后台有 ingest job 在跑。
2. **1970 K 线**：图表时间轴跑到 1970 年，K 线挤成一堵墙。sqlite 中该 `series_id` 的 `candle_time` 存在接近 0 的 Unix 秒数（如 `60`），属于典型脏数据。由于 `/replay` 依旧读同一份后端 DB，DB 一脏 live/replay 都中招。

涉及链路：`/ws/market`（订阅/断开 ondemand ingest）、`/api/backtest/*`（freqtrade 子进程）、`ccxt fetch_ohlcv`（网络/线程池阻塞）、`sqlite`（dev 下被复用导致脏数据）。

## 根因

1. **不可取消的阻塞工作**：同步 `subprocess.run()` 跑 freqtrade 或阻塞的网络请求会让 uvicorn 退出等待很久。
2. **资源泄漏**：WS 断开时若没有对称释放订阅引用，后台 ingest job 越积越多，表现为"越来越卡/最终假死"。
3. **DB 脏数据持续影响**：dev 环境复用同一份 sqlite（`backend/data/market.db`），历史脏数据持续影响渲染；缺少输入时间戳合理性的 fail-safe。

## 解法

1. **卡住先抓堆栈**（不靠猜）
   - 开启：`TRADE_CANVAS_ENABLE_FAULTHANDLER=1`（`scripts/dev_backend.sh` 默认开启）
   - 找 PID：`lsof -tiTCP:8000`
   - Dump：`kill -USR1 <pid>`（打印 all threads traceback）

2. **用可观测的状态快照判断泄漏**
   - 开启 debug：`TRADE_CANVAS_ENABLE_DEBUG_API=1`
   - 看 ondemand ingest：`GET /api/market/debug/ingest_state`（关注 `jobs` 数量、`refcount` 是否断开后仍不归零）

3. **外部依赖默认加超时**
   - freqtrade 子进程：`TRADE_CANVAS_FREQTRADE_SUBPROCESS_TIMEOUT_S`（默认 120s）
   - ccxt HTTP：`TRADE_CANVAS_CCXT_TIMEOUT_MS`（默认 10000ms）

4. **1970 时间轴先假设 DB 被污染**
   - 清 DB 再启动：`bash scripts/dev_backend.sh --restart --fresh-db`
   - 或仅清某个 series：`sqlite3 backend/data/market.db "delete from candles where series_id='...';"`

## 为什么有效

- 堆栈是最短路径：能直接把"卡住在哪"变成可讨论的事实（线程池/网络/子进程/锁）。
- refcount + debug snapshot 把"泄漏"量化，避免把"越来越慢"误判成"某个算法慢"。
- 默认超时把"无限等待"变成"可恢复失败"，对开发和实盘都更安全。

## 检查清单

**开发前**
- [ ] dev 启动前确认 DB 状态：是否需要 `--fresh-db`（避免被旧数据污染）。
- [ ] 明确本次链路的"可取消点"：子进程/网络/线程池是否有超时、是否能被 SIGINT 打断。

**开发中**
- [ ] 卡住时优先抓证据：`kill -USR1 <pid>` 打印所有线程堆栈（不要靠猜）。
- [ ] 对外部依赖（ccxt/freqtrade）默认带超时，避免无限等待。
- [ ] WS 订阅必须保证 subscribe/unsubscribe 对称；断开必须释放 refcount。

**验收时**
- [ ] 快速自检：`pytest -q`、`cd frontend && npm run build`。
- [ ] 如出现 1970：先查 DB：`sqlite3 backend/data/market.db "select min(candle_time), max(candle_time) from candles where series_id='...';"`

**排查流程（出现卡住/退不掉/端口残留/越来越慢时）**
1. `kill -USR1 <pid>` 抓堆栈
2. `GET /api/market/debug/ingest_state` 看 job/refcount 是否异常
3. 若涉及回测：确认子进程超时是否生效
4. 若时间轴异常：先清 DB（`--fresh-db`）排除脏数据

## 关联

- `scripts/dev_backend.sh`
- `backend/app/main.py`
- `backend/app/freqtrade_runner.py`
- `backend/app/ccxt_client.py`
- `backend/app/ingest_binance_ws.py`
