---
title: 复盘：后端“卡死/退不掉”与“1970 K 线”排查链路
status: done
created: 2026-02-02
updated: 2026-02-02
---

# 复盘：后端“卡死/退不掉”与“1970 K 线”排查链路

## 背景

最近几轮联调出现两类高频问题：

1) 后端跑一段时间会“卡住”，甚至 `Ctrl+C` 也不退出。
2) 图表时间轴跑到 1970 年，K 线挤成一堵墙（时间戳明显异常）。

涉及链路（证据：本次变更聚焦在这些点）：
- `/ws/market`：订阅/断开（ondemand ingest）
- `/api/backtest/*`：外部进程（freqtrade）
- `ccxt fetch_ohlcv`：网络/线程池阻塞
- `sqlite`：持久化状态在 dev 下被复用导致“脏数据”

## 具体错误（可复现现象/证据）

### A. “卡死/退不掉”

现象：
- 后端按 `Ctrl+C` 退出不干净，或看似退出但端口仍被占用（`scripts/dev_backend.sh` 报 port already in use）。

证据：
- 触发条件通常包括：开启图表（WS）、跑回测、或后台有 ingest job 在跑。
- 卡住时可以通过 `SIGUSR1` dump all threads 看到阻塞点（见“如何避免”）。

根因（聚合）：
1) **不可取消的阻塞工作**：同步 `subprocess.run()` 跑 freqtrade 或阻塞的网络请求会让 uvicorn 退出等待很久。
2) **资源泄漏**：WS 断开时若没有对称释放订阅引用，会导致后台 ingest job 越积越多，表现为“越来越卡/最终假死”。

### B. “1970 K 线”

现象：
- 右侧显示价格正常，但时间轴落在 1970 年附近，图形挤成竖线。

证据：
- sqlite 中该 `series_id` 的 `candle_time` 存在接近 0 的 Unix 秒数（例如 `60`），属于典型脏数据。
- 由于 `/replay` 目前只是 UI 模式标签，依旧读同一份后端 DB；所以 DB 一脏，live/replay 都会中招。

根因（1–3 条）：
1) dev 环境复用同一份 sqlite（`backend/data/market.db`），历史脏数据会持续影响渲染。
2) 缺少“输入时间戳合理性”的 fail-safe（例如拒收明显不可能的 candle_time）。

## 影响与代价

- 影响稳定性：卡死导致开发反馈链路断裂（端口占用、需要手工 kill）。
- 影响可信度：时间轴异常会让人误判“回放/数据源/渲染”哪一段坏了，定位成本上升。

## 如何避免（检查清单）

**开发前**
- [ ] dev 启动前确认 DB 状态：是否需要 `--fresh-db`（避免被旧数据污染）。
- [ ] 明确本次链路的“可取消点”：子进程/网络/线程池是否有超时、是否能被 SIGINT 打断。

**开发中**
- [ ] 卡住时优先抓证据：对后端进程 `kill -USR1 <pid>` 打印所有线程堆栈（不要靠猜）。
- [ ] 对外部依赖（ccxt/freqtrade）默认带超时，避免无限等待。
- [ ] WS 订阅必须保证 subscribe/unsubscribe 对称；断开必须释放 refcount。

**验收时**
- [ ] 快速自检：`pytest -q`、`cd frontend && npm run build`
- [ ] 如出现 1970：先查 DB：`sqlite3 backend/data/market.db "select min(candle_time), max(candle_time) from candles where series_id='...';"`

## 关联与证据

- 关键文件：
  - `backend/app/main.py`（WS 断开释放、freqtrade API 异步化、faulthandler）
  - `backend/app/freqtrade_runner.py`（可取消子进程 + 超时）
  - `backend/app/ingest_ccxt.py`（ccxt timeout）
  - `scripts/dev_backend.sh`（`--no-access-log`、`--fresh-db`）
- 验证命令：
  - `pytest -q`
  - `cd frontend && npm run build`

