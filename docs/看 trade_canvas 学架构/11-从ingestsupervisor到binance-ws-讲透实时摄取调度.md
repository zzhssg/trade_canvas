---
title: 第11关：从 IngestSupervisor 到 Binance WS——讲透实时摄取调度
status: done
created: 2026-02-11
updated: 2026-02-11
---

# 第11关：从 IngestSupervisor 到 Binance WS——讲透实时摄取调度

前面你学会了"数据怎么算"和"算崩了怎么办"。

但还有一个更基础的问题：**数据从哪来？**

交易所的行情数据是实时推送的，像一条永不停歇的河流。你的系统需要：

- 连上这条河（WebSocket 连接）
- 从河里取水（接收行情数据）
- 把水送到工厂（交给流水线处理）

听起来简单？但真实世界的河流不是那么好驯服的：

- 河流会断（网络断线）
- 你可能同时要从好几条河取水（多个交易对）
- 你的水桶有限（服务器资源有限）
- 有些河你一直需要（常用交易对），有些只是临时看看（用户临时订阅）

这一关，我们讲系统怎么管理这些"取水作业"。

---

## 1. 两层架构：调度员和取水工

系统把实时摄取分成两层，各管各的：

```text
┌─────────────────────────────────┐
│  IngestSupervisor（调度员）       │
│  管的是"作业"：                   │
│  - 哪些河该取水？                 │
│  - 水桶够不够？                   │
│  - 哪个取水工该休息了？            │
└──────────────┬──────────────────┘
               │ 启动/停止
               ▼
┌─────────────────────────────────┐
│  run_binance_ws_ingest_loop     │
│  （取水工）                      │
│  管的是"数据"：                   │
│  - 连上交易所 WS                 │
│  - 接收行情消息                   │
│  - 攒一批再送去处理               │
└─────────────────────────────────┘
```

为什么要分两层？

想象一个快递公司：调度中心（Supervisor）决定"今天派几辆车、跑哪些路线"，快递员（WS Loop）负责"开车、取件、送件"。调度中心不需要知道怎么开车，快递员不需要知道公司有几辆车。各管各的，互不干扰。

---

## 2. 调度员的核心：作业（Job）

每个"取水作业"在调度员眼里就是一个 Job：

```python
# backend/app/ingest_supervisor.py
@dataclass
class _Job:
    series_id: str              # 取哪条河（如 "binance:spot:BTC/USDT:1m"）
    stop: asyncio.Event         # 停止信号（喊一声就停）
    task: asyncio.Task          # 后台任务（取水工的工牌）
    source: str                 # 数据源（目前是 binance_ws）
    refcount: int               # 有几个人在看这条河
    last_zero_at: float | None  # 最后一次没人看的时间
    crashes: int = 0            # 崩了几次
    last_crash_at: float | None # 最后一次崩的时间
```

这里最关键的是 `refcount`——引用计数。它记录"有几个客户端正在订阅这个交易对"。

就像图书馆的借阅记录：一本书被 3 个人借了，`refcount = 3`。3 个人都还了，`refcount = 0`，这本书就可以放回仓库了。

---

## 3. 两种作业：常驻 vs 按需

### 常驻作业（白名单）

有些交易对是"镇馆之宝"——不管有没有人看，都要一直取数据。比如 BTC/USDT，它是最重要的交易对，系统启动就开始取。

```python
# 白名单作业的 refcount = -1，表示"永不回收"
def start_whitelist(self):
    for series_id in self._whitelist_series_ids:
        job = self._start_job(series_id, refcount=-1)  # -1 = 常驻
        self._jobs[series_id] = job
```

`refcount = -1` 是一个特殊标记，意思是"这个作业是 VIP，不参与淘汰"。

### 按需作业（用户订阅）

用户在前端打开了 ETH/USDT 的图表，系统才开始取 ETH 的数据。用户关了图表，过一会儿就停止取数据。

```python
# 用户订阅时
async def subscribe(self, series_id):
    job = self._jobs.get(series_id)
    if job is None:
        job = self._start_job(series_id, refcount=0)  # 新建作业
        self._jobs[series_id] = job
    job.refcount += 1       # 多一个人在看
    job.last_zero_at = None # 有人看了，不算空闲

# 用户退订时
async def unsubscribe(self, series_id):
    job = self._jobs.get(series_id)
    if job is None:
        return
    job.refcount = max(0, job.refcount - 1)  # 少一个人在看
    if job.refcount == 0:
        job.last_zero_at = time.time()  # 记录"没人看了"的时间
```

就像出租车：有些是固定线路的公交车（白名单），风雨无阻；有些是打车叫来的（按需），乘客下车了就可以走了。

---

## 4. 容量治理：水桶不够了怎么办

### 问题：服务器资源有限

每个 WS 连接都占用内存和 CPU。如果用户同时订阅了 100 个交易对，服务器可能扛不住。

### 解决：容量上限 + 智能淘汰

系统有一个 `ondemand_max_jobs` 参数，限制按需作业的数量。当容量满了，新的订阅请求怎么办？

```text
新订阅请求来了
  ├─ 容量没满 → 直接创建新作业 ✅
  └─ 容量满了
       ├─ 有空闲作业（refcount=0）→ 淘汰最早空闲的，腾出位置 ✅
       └─ 没有空闲作业 → 拒绝订阅 ❌
```

核心代码（简化版）：

```python
# backend/app/ingest_supervisor.py
async def subscribe(self, series_id):
    async with self._lock:
        job = self._jobs.get(series_id)
        if job is None:
            max_jobs = self._ondemand_max_jobs
            if max_jobs > 0:
                ondemand_jobs = [j for sid, j in self._jobs.items()
                                if not self._is_pinned_whitelist(sid)]
                if len(ondemand_jobs) >= max_jobs:
                    # 找最早空闲的作业淘汰
                    idle = [j for j in ondemand_jobs
                           if j.refcount == 0 and j.last_zero_at is not None]
                    idle.sort(key=lambda j: j.last_zero_at)
                    if idle:
                        victim = idle[0]       # 最早空闲的
                        self._jobs.pop(victim.series_id)
                        victim.stop.set()      # 通知停止
                        victim.task.cancel()   # 取消任务
                    else:
                        return False           # 没有可淘汰的，拒绝
            job = self._start_job(series_id, refcount=0)
            self._jobs[series_id] = job
        job.refcount += 1
    return True
```

注意淘汰策略：**优先淘汰最早空闲的**。不是随机踢，也不是踢最新的，而是踢"没人看、而且没人看的时间最长"的那个。

就像停车场满了，新车要进来。管理员不会随便拖走一辆车，而是先看哪辆车停得最久、车主也不在——拖走那辆。

---

## 5. 空闲回收：忘记退订的保险丝

### 问题：客户端断线了，没来得及退订

用户关了浏览器，WebSocket 断了，但 `unsubscribe` 没被调用。这个作业的 `refcount` 永远不会归零，资源就泄漏了。

### 解决：Idle Reaper（空闲收割机）

调度员有一个后台循环，每秒扫一次所有作业：

```text
Idle Reaper 的逻辑：
  对每个非白名单作业：
    如果 refcount == 0
    且 空闲时间 > ondemand_idle_ttl_s（比如 60 秒）
    → 停止作业，释放资源
```

就像商场的自动扶梯：没人站上去超过一段时间，就自动停下来省电。有人来了再启动。

这个机制保证了：即使客户端"忘记退订"，资源也不会永远被占着。

---

## 6. 取水工：WS 摄取循环

调度员管"派谁去"，取水工管"怎么取"。取水工的核心是 `run_binance_ws_ingest_loop`。

### 连接交易所

```python
# backend/app/ingest_binance_ws.py
def build_binance_kline_ws_url(series):
    stream_symbol = "btcusdt"  # "BTC/USDT" → "btcusdt"
    tf = "1m"
    # 期货
    return f"wss://fstream.binance.com/ws/{stream_symbol}@kline_{tf}"
    # 现货
    return f"wss://stream.binance.com:9443/ws/{stream_symbol}@kline_{tf}"
```

### 消息分流：forming vs closed

交易所推送的每条消息里有一个关键字段 `is_final`：

```python
def parse_binance_kline_payload_any(payload):
    k = payload.get("k")
    is_final = bool(k.get("x"))  # x=true 表示这根蜡烛收盘了
    candle = CandleClosed(
        candle_time=int(k["t"]) // 1000,  # 毫秒转秒
        open=float(k["o"]),
        high=float(k["h"]),
        low=float(k["l"]),
        close=float(k["c"]),
        volume=float(k["v"]),
    )
    return candle, is_final
```

- `is_final = False`：这根蜡烛还在跳动（forming），只用来更新图表显示，不进因子计算
- `is_final = True`：这根蜡烛收盘了（closed），要进入完整的写入流水线

就像考试：铃响之前你还在写（forming），铃响了才交卷（closed）。老师只批改交了的卷子，不批改你还在写的。

### forming 的节流

forming 消息可能每秒来好几条（价格一直在跳）。如果每条都推给前端，太浪费了。系统有一个最小间隔：

```python
# 默认 250ms，即每秒最多推 4 次 forming 更新
if (now - last_forming_emit_at) >= forming_min_interval_s:
    await hub.publish_forming(series_id=series_id, candle=candle)
    last_forming_emit_at = now
```

就像股票行情软件：价格每毫秒都在变，但屏幕上每秒刷新 4 次就够了。人眼分辨不出更快的变化。

---

## 7. 攒批刷盘：不是来一根处理一根

### 问题：每根蜡烛都立刻处理，太浪费

如果每收到一根 closed 蜡烛就立刻跑一次完整的写入流水线（存库 → 因子 → 覆盖层），开销太大。特别是补数据的时候，可能一下子来几十根。

### 解决：缓冲 + 双触发刷新

```python
# backend/app/ingest_binance_ws.py（简化版）
buf: list[CandleClosed] = []       # 缓冲区
last_flush_at = time.time()

while not stop.is_set():
    candle, is_final = parse(message)

    if not is_final:
        publish_forming(candle)     # forming 直接推
        continue

    buf.append(candle)              # closed 先攒着

    # 两个触发条件，满足任一就刷盘
    if len(buf) >= batch_max or (time.time() - last_flush_at) >= flush_s:
        await flush("threshold")
```

两个刷盘触发条件：

| 条件 | 默认值 | 白话 |
| ---- | ---- | ---- |
| `batch_max` | 200 | 攒够 200 根就刷 |
| `flush_s` | 0.5 秒 | 超过半秒没刷就刷 |

就像快递分拣：不是每收到一个包裹就发一趟车，而是"攒够一车"或"等了半小时"就发车。既不浪费运力，也不让包裹等太久。

### 刷盘时的去重

刷盘前会做两件事：排序 + 去重。

```python
async def flush(reason):
    buf.sort(key=lambda c: c.candle_time)  # 按时间排序
    deduped = []
    for candle in buf:
        if candle.candle_time <= last_emitted_time:
            continue  # 跳过已处理过的
        deduped.append(candle)
    # 交给 pipeline 处理
    await ingest_pipeline.run(batches={series_id: deduped}, publish=False)
```

为什么要去重？因为网络抖动可能导致同一根蜡烛被收到两次。去重保证不会重复处理。

---

## 8. 先写后发：不让前端看到"半成品"

### 问题：如果先发消息再写库会怎样？

假设系统先通过 WebSocket 告诉前端"新蜡烛来了"，再写入数据库。前端收到消息后去查数据库，但数据还没写进去——前端看到的是空的。

### 解决：publish after persist

```python
# 先写库（不发消息）
pipeline_result = await ingest_pipeline.run(
    batches=all_batches,
    publish=False,          # 注意：不发消息！
)

# 写完了，再统一发消息
await _publish_pipeline_result_from_ws(
    series_id=series_id,
    pipeline_result=pipeline_result,
)
```

先写后发，保证前端收到消息时，数据已经在库里了。

就像餐厅上菜：厨师做好了才喊"菜来了"，不会菜还在锅里就喊。否则服务员端着空盘子去找客人，多尴尬。

---

## 9. 派生时间框架：一条河变多条

### 问题：5分钟线、15分钟线、1小时线……每个都要连一条 WS？

如果用户同时看 1m、5m、15m、1h 四个时间框架，要连 4 条 WS 吗？那 100 个交易对就是 400 条连接，服务器扛不住。

### 解决：只连 1m，其他本地合成

系统只连 1 分钟线的 WS（基础时间框架），5m、15m、1h 都由本地从 1m 数据合成：

```text
交易所 WS（1m）
  │
  ├─ 直接使用 → 1m 蜡烛
  │
  └─ 本地合成
       ├─ 5 根 1m → 1 根 5m
       ├─ 15 根 1m → 1 根 15m
       └─ 60 根 1m → 1 根 1h
```

合成逻辑很直觉：

```python
def _merge_candles_to_derived(*, bucket_open_time, minutes):
    return CandleClosed(
        candle_time=bucket_open_time,
        open=minutes[0].open,           # 第一根的开盘价
        high=max(c.high for c in minutes),   # 所有的最高价
        low=min(c.low for c in minutes),     # 所有的最低价
        close=minutes[-1].close,        # 最后一根的收盘价
        volume=sum(c.volume for c in minutes),  # 总成交量
    )
```

就像做月报：你不需要每个月重新统计一遍原始数据，只需要把 4 个周报合并就行。周报的数据已经是准确的了。

这个设计的好处巨大：

- 连接数不随时间框架数增长（1 条 vs N 条）
- 所有时间框架的数据口径一致（都来自同一个 1m 源）
- 调度层复杂度不爆炸

---

## 10. 断线重连：河流断了怎么办

WS 连接随时可能断。系统的策略很简单：等 2 秒，重连。

```python
while not stop.is_set():
    try:
        async with websockets.connect(url, ...) as upstream:
            while not stop.is_set():
                raw = await upstream.recv()
                # ... 处理消息 ...
    except asyncio.CancelledError:
        return              # 被调度员叫停了，正常退出
    except Exception:
        await asyncio.sleep(2.0)  # 断线了，等 2 秒重连
```

同时，调度员会记录崩溃次数：

```python
# 调度员记录崩溃信息
job.crashes += 1
job.last_crash_at = time.time()
```

这样运维可以通过 debug snapshot 看到"哪个交易对在频繁崩"，快速定位问题。

不是无限立即重试（会把 CPU 打满），也不是崩了就放弃（会丢数据）。等 2 秒是一个简单但有效的折中。

---

## 11. 一个完整的生命周期

把所有环节串起来，看一个按需作业的完整生命周期：

```text
① 用户打开 ETH/USDT 图表
   → 前端发 WS subscribe
   → 调度员创建 Job，refcount=1
   → 启动取水工，连接 Binance WS

② 取水工开始工作
   → 收到 forming 消息 → 节流后推给前端（图表实时跳动）
   → 收到 closed 消息 → 攒入缓冲区
   → 缓冲区满了 → 刷盘（先写库，再发消息）

③ 另一个用户也打开了 ETH/USDT
   → 调度员 refcount++ → refcount=2
   → 不会重复创建作业（复用已有的）

④ 两个用户都关了图表
   → 调度员 refcount-- → refcount=0
   → 记录 last_zero_at

⑤ 60 秒后，Idle Reaper 扫到这个作业
   → 空闲超时，停止作业
   → 取水工收到 stop 信号，断开 WS，退出

⑥ 如果中途 WS 断线
   → 取水工等 2 秒重连
   → 调度员记录 crashes++
```

---

## 12. 这关的四条可迁移原则

```text
原则1：Control plane / Data plane 分离
  → 调度器管作业生命周期，循环管数据处理
  → 各管各的，互不干扰

原则2：Capacity with graceful degradation（优雅降级的容量控制）
  → 满载时先淘汰空闲，实在不行明确拒绝
  → 不是"崩了"，而是"有序地说不"

原则3：One source, many derived（一源多派生）
  → 只连一条基础流，其他时间框架本地合成
  → 连接数不随维度爆炸

原则4：Publish after persist（先写后发）
  → 先写库再发消息，前端不会看到半成品
  → 数据一致性优先于实时性
```

---

## 13. 代码锚点

| 概念 | 文件 | 干什么的 |
| ---- | ---- | ---- |
| 调度员 | `backend/app/ingest_supervisor.py` | 作业生命周期 + 容量治理 |
| 取水工 | `backend/app/ingest_binance_ws.py` | WS 连接 + 消息处理 + 攒批 |
| 运行时装配 | `backend/app/market_runtime_builder.py` | 各组件如何拼装 |
| WS 路由 | `backend/app/market_ws_routes.py` | 前端订阅的入口 |
| 容量测试 | `backend/tests/test_ingest_supervisor_capacity.py` | 容量控制场景覆盖 |

---

## 14. 过关自测

如果你能用自己的话回答这五个问题，第 11 关就过了：

1. 白名单作业的 `refcount = -1` 是什么意思？为什么不用 `refcount = 999999`？
2. 容量满了时，系统怎么决定淘汰谁？用"停车场"的比喻解释。
3. 为什么 forming 消息要节流，而 closed 消息不节流？
4. 攒批刷盘的两个触发条件分别是什么？为什么需要两个？
5. 为什么派生时间框架要从 1m 本地合成，而不是每个时间框架都连一条 WS？
