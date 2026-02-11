---
title: 第12关：从 gap backfill 到 tail coverage——讲透历史缺口修复策略
status: done
created: 2026-02-11
updated: 2026-02-11
---

# 第12关：从 gap backfill 到 tail coverage——讲透历史缺口修复策略

前一关你学会了实时数据怎么进来。但实时数据有一个天然的弱点：**它只管"现在"，不管"过去"。**

你刚启动系统，数据库是空的。用户打开图表，想看最近 2000 根蜡烛——但你只有刚收到的那一根。

或者更常见的情况：网络断了 10 分钟，重连后直接收到了最新的蜡烛，中间 10 根就丢了。

这些"洞"不会自己消失。你必须主动去补。

就像你搬进新家，书架是空的。你不能等书自己飞过来——你得去书店买、去图书馆借、找朋友要。而且不同的"缺书"情况，补法不一样。

---

## 1. 三种"洞"，三种补法

系统面临三种不同的数据缺口，每种有不同的成因和修复策略：

```text
┌─────────────────────────────────────────────────────┐
│ 第一种：连接缺口（Gap）                               │
│ 场景：WS 断线 10 分钟，重连后中间少了 10 根蜡烛        │
│ 特点：知道缺口的精确范围                               │
│ 补法：从历史数据源精确补填                              │
├─────────────────────────────────────────────────────┤
│ 第二种：尾部不足（Tail Coverage）                      │
│ 场景：用户要看 2000 根，数据库只有 500 根               │
│ 特点：知道"还差多少"，但不知道精确缺哪些                │
│ 补法：从多个数据源逐级补填                              │
├─────────────────────────────────────────────────────┤
│ 第三种：冷启动空窗（Startup Sync）                     │
│ 场景：服务刚启动，数据库完全是空的                       │
│ 特点：什么都没有，需要从零开始                           │
│ 补法：启动时批量导入历史数据                             │
└─────────────────────────────────────────────────────┘
```

就像医院的三种病人：急诊（Gap，知道哪里断了，赶紧接上）、体检（Tail，整体检查一遍，哪里不够补哪里）、新生儿（Startup，从零开始建档）。

---

## 2. 第一种洞：连接缺口（Gap Backfill）

### 问题：WS 断线后，中间的蜡烛丢了

假设你上次收到的蜡烛时间是 160（代表 16:00），时间框架是 1 分钟。下一根应该是 161（16:01）。但 WS 断了，重连后直接收到了 170（16:10）。

中间 161-169 这 9 根蜡烛就是"缺口"。

### 解决：先补后发

系统在发送蜡烛给前端之前，会检查有没有缺口：

```python
# backend/app/ws_hub.py（简化版）
async def _prepare_sendable_with_gap(self, *, series_id, sub, candles_sorted):
    # 计算"期望的下一根"
    expected_next = sub.last_sent_time + sub.timeframe_s  # 160 + 60 = 161

    first_time = candles_sorted[0].candle_time  # 实际收到的是 170

    if first_time > expected_next:
        # 检测到缺口！尝试补填
        recovered = await self._recover_gap_candles(
            series_id=series_id,
            expected_next_time=expected_next,  # 161
            actual_time=first_time,            # 170
        )
        if recovered:
            candles_sorted = merge(recovered + candles_sorted)  # 补上后合并

    # 如果补完还有缺口，告诉前端"这里有断层"
    if candles_sorted[0].candle_time > expected_next:
        return candles_sorted, gap_payload  # 带缺口标记
    return candles_sorted, None             # 无缺口
```

关键策略：**先治后报**。

- 能补上 → 补上后正常发送，前端无感知
- 补不上 → 发一个 `gap` 消息告诉前端"这里有断层"

就像快递丢了几个包裹：快递公司先尝试找回来。找回来了就正常送；找不回来就通知你"这几个包裹丢了"。不会假装什么都没发生。

### 补填的具体策略

缺口补填会尝试多个数据源：

```python
# backend/app/market_backfill.py（简化版）
def backfill_market_gap_best_effort(*, store, series_id, expected_next_time, actual_time, ...):
    start = expected_next_time   # 缺口起点
    end = actual_time - tf_s     # 缺口终点

    before = store.count_closed_between_times(series_id, start, end)  # 补前有几根

    # 策略1：从 Freqtrade 历史文件补
    try:
        backfill_tail_from_freqtrade(store, series_id=series_id, limit=target)
    except Exception:
        pass  # 失败了不要紧，还有下一招

    # 策略2：从交易所 API（CCXT）补
    if enable_ccxt_backfill:
        try:
            backfill_from_ccxt_range(store, series_id=series_id, start_time=start, end_time=end)
        except Exception:
            pass

    after = store.count_closed_between_times(series_id, start, end)  # 补后有几根
    return after - before  # 返回补了几根
```

注意：每个策略都用 `try/except` 包着，失败了不会崩，继续尝试下一个。这就是"最佳努力"（best-effort）——能补多少补多少，补不了的不强求。

---

## 3. 第二种洞：尾部不足（Tail Coverage）

### 问题：数据库里的蜡烛不够用

用户打开图表，请求最近 2000 根蜡烛。但数据库里只有 500 根。这不是"中间断了"，而是"尾巴不够长"。

### 解决：四级补填决策树

系统用一个四级策略来补尾，像一个逐级升级的求助链：

```text
第一级：问 Freqtrade（本地文件）
  ├─ 成功 → 检查够不够
  └─ 失败 → 继续
       ↓
第二级：从 1m 基础数据合成（本地计算）
  ├─ 成功 → 检查够不够
  └─ 失败/不适用 → 继续
       ↓
第三级：问交易所 API（CCXT，需要网络）
  ├─ 成功 → 检查够不够
  └─ 失败/未启用 → 继续
       ↓
第四级：记录结果，报告"补了多少，还差多少"
```

就像你缺书：先翻自己的旧箱子（Freqtrade 本地文件）→ 再看能不能用手头的材料拼（1m 合成 5m）→ 再去网上买（交易所 API）→ 最后记录"还差哪几本"。

为什么要分四级？因为每一级的成本不同：

| 级别 | 数据源 | 成本 | 速度 |
| ---- | ---- | ---- | ---- |
| 第一级 | Freqtrade 本地文件 | 零（读磁盘） | 最快 |
| 第二级 | 1m 数据本地合成 | 零（CPU 计算） | 快 |
| 第三级 | 交易所 API（CCXT） | 有（网络请求，有限速） | 慢 |

能用免费的就不花钱，能用快的就不用慢的。

### 第二级的巧妙之处：本地合成

如果用户要看 5 分钟线，而数据库里有足够的 1 分钟线，系统可以直接从 1m 合成 5m，不需要出网：

```python
# 5 根 1m 蜡烛合成 1 根 5m 蜡烛
def _merge_candles_to_derived(*, bucket_open_time, minutes):
    return CandleClosed(
        candle_time=bucket_open_time,
        open=minutes[0].open,                    # 第一根的开盘价
        high=max(c.high for c in minutes),       # 所有的最高价
        low=min(c.low for c in minutes),         # 所有的最低价
        close=minutes[-1].close,                 # 最后一根的收盘价
        volume=sum(c.volume for c in minutes),   # 总成交量
    )
```

这和第 11 关讲的"派生时间框架"是同一个思路：**能本地算就不出网。**

### 第三级的安全阀：不是随便就能调交易所 API

CCXT 补填不是默认开启的，需要同时满足两个条件：

```python
# 两个条件都满足才会调 CCXT
allow_ccxt = (to_time is not None) or enable_ccxt_backfill_on_read
if count_after_tail < target and enable_ccxt_backfill and allow_ccxt:
    backfill_from_ccxt_range(...)
```

为什么这么谨慎？因为交易所 API 有限速（rate limit），调太多会被封。就像你不能每天去图书馆借 100 本书——图书馆会限制你的借阅量。

### 读路径触发补填：顺手修补

一个很聪明的设计：补填不是靠后台定时任务，而是在用户读数据时"顺手"触发。

```python
# backend/app/market_http_routes.py（简化版）
# 用户请求 GET /api/market/candles?limit=2000
if enable_market_auto_tail_backfill:
    ensure_tail_coverage(series_id=series_id, target_candles=2000)
# 然后正常读数据返回
candles = store.get_closed(series_id, limit=2000)
```

用户来读数据 → 系统发现不够 → 顺手补一下 → 返回补完的数据。

就像你去餐厅点菜，服务员发现盐用完了，顺手去厨房拿了一瓶。你不需要自己去拿，也不需要等专门的"补盐员"。

---

## 4. 第三种洞：冷启动空窗（Startup Sync）

### 问题：服务刚启动，什么数据都没有

服务器重启了，数据库是空的（或者很久没更新了）。第一个用户打开图表，看到一片空白。

### 解决：启动时批量追平

系统在启动后、接受用户请求之前，先把白名单里的交易对数据补齐：

```text
服务启动
  ↓
对每个白名单 series：
  ① 计算"现在应该有数据到几点"（target_time）
  ② 调 ensure_tail_coverage 补到 target_time
  ③ 触发 pipeline.refresh_series_sync 让因子/覆盖层跟上
  ↓
输出统计：synced 3 / lagging 1 / errors 0
  ↓
开始接受用户请求
```

这就是把"首屏空洞"从用户体验问题，前移为启动治理问题。

就像餐厅开门前的准备工作：不是等客人来了才开始洗菜切菜，而是提前备好。客人一来就能上菜。

---

## 5. CCXT 补填的分页逻辑

从交易所 API 拉数据不是一次就能拉完的。交易所有单次请求的数量限制（比如最多 1000 根）。系统用分页循环来处理：

```python
# backend/app/market_backfill.py（简化版）
def backfill_from_ccxt_range(*, candle_store, series_id, start_time, end_time, batch_limit=1000):
    since_ms = start_time * 1000  # 交易所用毫秒

    while since_ms <= end_time * 1000:
        # 拉一批
        rows = exchange.fetch_ohlcv(symbol, timeframe, since_ms, batch_limit)
        if not rows:
            break  # 没数据了

        # 写入数据库
        candles = [CandleClosed(candle_time=row[0]//1000, ...) for row in rows]
        store.upsert_many_closed_in_conn(conn, series_id, candles)

        # 移动游标到下一批
        max_time = max(row[0] for row in rows)
        next_since_ms = (max_time // 1000 + tf_s) * 1000
        if next_since_ms <= since_ms:
            break  # 防止死循环
        since_ms = next_since_ms
```

注意最后的防死循环检查：如果游标没有前进（`next_since_ms <= since_ms`），说明出了问题，立刻退出。不会傻傻地一直请求同一批数据。

---

## 6. 补填进度追踪：补了多少，还差多少

### 问题：补填是黑箱吗？

如果补填过程没有任何可观测性，你只能祈祷它成功了。出了问题也不知道补到哪了。

### 解决：进度追踪器

```python
# backend/app/market_backfill_tracker.py
class MarketBackfillProgressTracker:
    def begin(self, *, series_id, start_missing_seconds, start_missing_candles, reason):
        # 记录：开始补填，初始缺了多少
        state = "running"

    def succeed(self, *, series_id, current_missing_seconds, current_missing_candles, note):
        # 记录：补填完成，还缺多少
        state = "succeeded"
        note = "tail_coverage_done"      # 全补齐了
        # 或
        note = "tail_coverage_partial"   # 补了一部分

    def fail(self, *, series_id, current_missing_seconds, current_missing_candles, error):
        # 记录：补填失败，原因是什么
        state = "failed"
```

这些进度数据会汇总到健康检查 API：

```text
GET /api/market/health

{
  "BTCUSDT:1h": {
    "state": "green",        // 已追平
    "head_time": 1707007200,
    "lag_seconds": 0
  },
  "ETHUSDT:5m": {
    "state": "yellow",       // 正在补，还有缺口
    "head_time": 1707003600,
    "lag_seconds": 3600,
    "backfill_progress_pct": 75
  }
}
```

运维一看就知道：BTC 没问题，ETH 还在补，补了 75%。

就像工地的进度看板：不是问"盖好了没"，而是"盖到第几层了，还差几层"。

---

## 7. 所有补填开关一览

每种补填能力都有独立的开关，可以单独开关：

| 开关 | 控制什么 | 默认 |
| ---- | ---- | ---- |
| `ENABLE_MARKET_GAP_BACKFILL` | WS 缺口补填 | 关 |
| `ENABLE_MARKET_AUTO_TAIL_BACKFILL` | 读路径自动补尾 | 关 |
| `ENABLE_CCXT_BACKFILL` | 允许调交易所 API | 关 |
| `ENABLE_CCXT_BACKFILL_ON_READ` | 读路径允许调 CCXT | 关 |
| `ENABLE_STARTUP_KLINE_SYNC` | 启动时追平 | 关 |
| `ENABLE_DERIVED_TIMEFRAMES` | 派生时间框架合成 | 关 |

为什么默认都关？因为每个开关都有成本：

- 缺口补填 → 额外的磁盘读写
- CCXT → 网络请求，可能被限速
- 启动追平 → 延长启动时间

就像汽车的辅助驾驶功能：车道保持、自动刹车、自适应巡航……每个都有用，但你得根据路况决定开哪些。高速公路全开，停车场全关。

---

## 8. 一个完整的补填场景

假设：服务运行中，用户请求 ETHUSDT 5m 最近 500 根蜡烛，数据库只有 200 根。

```text
① 用户请求 GET /api/market/candles?series_id=ETHUSDT:5m&limit=500

② 系统检测到 auto_tail_backfill 开启
   → 调 ensure_tail_coverage(target=500)

③ 第一级：Freqtrade
   → 找到本地文件，导入了 100 根
   → 现在有 300 根，还差 200

④ 第二级：从 1m 合成
   → 数据库有足够的 1m 数据
   → 合成了 150 根 5m 蜡烛
   → 现在有 450 根，还差 50

⑤ 第三级：CCXT
   → enable_ccxt_backfill=True，allow_ccxt=True
   → 从交易所拉了 50 根
   → 现在有 500 根，够了！

⑥ 进度追踪器记录：
   state=succeeded, note="tail_coverage_done"

⑦ 返回 500 根蜡烛给用户
```

整个过程对用户来说是透明的——他只是请求了数据，系统在背后默默补齐了。

---

## 9. 这关的五条可迁移原则

```text
原则1：分层治理同一问题
  → 连接层洞、存储层洞、启动层洞分别处理
  → 不要试图用一个函数解决所有缺口

原则2：Best-effort + 显式告警
  → 先补，补不齐就明确暴露（发 gap 消息、记录 partial）
  → 不偷偷跳过，不假装没事

原则3：本地优先，外部兜底
  → 先 Freqtrade 本地文件 → 再 1m 本地合成 → 最后交易所 API
  → 能不出网就不出网

原则4：开关化放量
  → 所有高成本补填能力都能 kill-switch
  → 按环境和风险逐步放开

原则5：结果可量化
  → 每次补填都有"进度、状态、原因"
  → 补填策略必须配健康视图，否则就是玄学调参
```

---

## 10. 代码锚点

| 概念 | 文件 | 干什么的 |
| ---- | ---- | ---- |
| WS 缺口检测 | `backend/app/ws_hub.py` | _prepare_sendable_with_gap |
| 缺口补填 | `backend/app/market_backfill.py` | backfill_market_gap_best_effort |
| 尾部补填 | `backend/app/market_data/read_services.py` | ensure_tail_coverage 四级决策树 |
| CCXT 分页拉取 | `backend/app/market_backfill.py` | backfill_from_ccxt_range |
| Freqtrade 导入 | `backend/app/history_bootstrapper.py` | maybe_bootstrap / backfill_tail |
| 派生合成 | `backend/app/market_data/derived_services.py` | 从 1m 合成派生时间框架 |
| 进度追踪 | `backend/app/market_backfill_tracker.py` | begin/succeed/fail |
| 健康检查 | `backend/app/market_health_service.py` | green/yellow/red 状态 |
| 启动追平 | `backend/app/startup_kline_sync.py` | run_startup_kline_sync |

---

## 11. 过关自测

如果你能用自己的话回答这五个问题，第 12 关就过了：

1. Gap 和 Tail Coverage 为什么必须分两条治理链？用"急诊 vs 体检"的比喻解释。
2. ensure_tail_coverage 的四级策略为什么按"本地文件 → 本地合成 → 交易所 API"的顺序？如果反过来会怎样？
3. 为什么 CCXT 补填默认不开启？在什么场景下应该开启？
4. WS 层检测到缺口后，为什么要"先补后报"而不是直接发 gap 消息？
5. 补填进度追踪器的 `tail_coverage_done` 和 `tail_coverage_partial` 分别代表什么？为什么需要区分？
