---
title: 第15关：从 WS 协议到 catchup 机制，讲透客户端时序一致性
status: done
created: 2026-02-11
updated: 2026-02-11
---

# 第15关：从 WS 协议到 catchup 机制，讲透客户端时序一致性

前面你学了后端怎么写、怎么读、前后端怎么签合同。

这一关要解决一个更刺激的问题：**实时推送。**

HTTP 是"你问我答"——前端问一次，后端答一次。但量化交易不能每秒钟问一次"有没有新蜡烛"，那太慢也太浪费。

所以系统用 WebSocket（WS）：后端有新数据就主动推给前端，不用前端反复问。

但 WS 推送有一个 HTTP 没有的难题：

**客户端刚连上来，它落后了 50 根蜡烛。你是先补历史，还是先推实时？补历史的时候新蜡烛来了怎么办？补完历史和实时之间有没有重复？有没有遗漏？**

这就像你迟到了 50 分钟进电影院。你是先看之前的剧情回放，还是直接看现在的画面？回放的时候电影还在继续放，回放结束后怎么无缝接上？

trade_canvas 的 WS 链路，就是专门解这个"迟到观众"问题的。

---

## 1. 先给一句总纲

客户端时序一致性的核心是一个游标：

**每个连接维护一份 `last_sent_time`，所有发送（无论是补历史还是推实时）都以"只发大于 last_sent 的蜡烛"作为硬门槛。**

就像电影院的进度条：不管你是看回放还是看直播，进度条只往前走，不往回倒。

---

## 2. WS 协议：先把"能说什么话"定死

在讲具体流程之前，先看协议层。

### 2.1 消息类型是枚举，不是自由文本

```python
# 入站（客户端 → 服务器）
"subscribe"      # 订阅某个 series
"unsubscribe"    # 取消订阅

# 出站（服务器 → 客户端）
"candle_closed"   # 单根已收盘蜡烛
"candles_batch"   # 批量已收盘蜡烛（catchup 时用）
"candle_forming"  # 正在形成的蜡烛（实时预览）
"gap"             # 时序间隙通知
"system"          # 系统事件
"error"           # 错误
```

为什么要枚举？因为前端可以写确定性的状态机：

```typescript
// 前端消息处理
type MarketWsMessage =
  | { type: "candle_forming"; candle: CandleClosed }
  | { type: "candle_closed"; candle: CandleClosed }
  | { type: "candles_batch"; candles: CandleClosed[] }
  | { type: "gap"; expected_next_time?: number; actual_time?: number }
  | { type: "error"; code?: string; message?: string }
  | { type: "system"; event?: string };
```

就像对讲机的呼号规范：你只能说"收到""明白""请求支援"这几种，不能自由发挥。这样对方才能快速理解你在说什么。

### 2.2 错误码也是固定的

```python
"bad_request"   # 请求格式错误
"capacity"      # 容量不足，无法订阅
```

前端看到 `capacity` 就知道"服务器忙不过来了"，不用猜字符串。

---

## 3. 订阅握手：不是"连上就推"，而是一次带时序治理的握手

客户端发送 subscribe 后，服务器不是立刻开始推实时数据。它会走一个完整的流程：

```text
客户端                              服务器
  |                                   |
  |--- subscribe(since=100) -------->|
  |                                   |
  |                            ① 派生数据初始化
  |                            ② Hub 注册订阅
  |                            ③ 读取历史蜡烛
  |                            ④ 计算 effective_since
  |                            ⑤ 检测并修复间隙
  |                            ⑥ 构造发送消息
  |                            ⑦ 更新 last_sent_time
  |                                   |
  |<--- candles_batch [160,220] -----|
  |                                   |
  |<--- candle_closed(280) ----------|  ← 实时推送开始
```

这个流程就像电影院的"迟到观众服务"：

1. 先确认你的座位（Hub 注册）；
2. 查你上次看到哪里（since=100）；
3. 把你没看过的剧情快速回放（catchup）；
4. 回放结束后无缝接上正在播放的画面（live）。

---

## 4. effective_since：防重复的核心公式

客户端说"我上次看到第 100 秒"（since=100）。但如果这个连接之前已经收过一些数据呢？

比如客户端先订阅了一次，收到了 160 和 220，然后断线重连，又发了 subscribe(since=100)。如果服务器老老实实从 100 开始补，160 和 220 就会被发两次。

所以系统用一个公式：

```text
effective_since = max(since, last_sent_time)
```

- `since` 是客户端声称的"我看到哪里了"；
- `last_sent_time` 是服务器记录的"我给你发到哪里了"；
- 取较大值，确保不重复。

就像图书馆的借书记录：你说"我上次借到第 3 本"，但系统记录你已经借到第 5 本了。那就从第 6 本开始给你，不会重复给第 3~5 本。

---

## 5. last_sent_time：每个连接的"进度条"

这是整个 WS 时序一致性的基石。

```python
@dataclass
class _Subscription:
    series_id: str
    last_sent_time: int | None   # 最后发送的蜡烛时间
    timeframe_s: int             # 时间框架秒数
    supports_batch: bool         # 是否支持批量
```

每个连接的每个订阅都有自己的 `last_sent_time`。所有发送操作都必须检查这个值：

```python
@staticmethod
def _should_skip_candle(*, sub: _Subscription, candle_time: int) -> bool:
    if sub.last_sent_time is None:
        return False
    return int(candle_time) <= int(sub.last_sent_time)
```

规则极其简单：**蜡烛时间 <= last_sent_time 的，一律跳过。**

就像电影院的进度条：已经播过的片段，不管什么原因，都不会再播一次。

这个检查在两个地方执行：
1. catchup 阶段：构建历史数据时过滤；
2. live 阶段：Hub 推送实时数据时过滤。

双重保险，确保同一根蜡烛绝不重复发送。

---

## 6. Gap 检测："中间少了几集"怎么办

### 6.1 什么是 gap

服务器知道"上次发到第 220 秒，下一根应该是第 280 秒"。结果实际收到的第一根是第 400 秒。中间少了 280~340 这几根。

```python
@staticmethod
def _expected_next_time(sub: _Subscription) -> int | None:
    if sub.last_sent_time is None:
        return None
    return int(sub.last_sent_time) + int(sub.timeframe_s)
```

如果 `actual_time > expected_next_time`，就是 gap。

就像追剧：你看完第 5 集，下一集应该是第 6 集。结果平台直接跳到第 9 集。中间少了 6、7、8 三集。

### 6.2 先治后报：能补就补，补不了再通知

发现 gap 后，系统不是立刻告诉前端"有洞"。它会先尝试自愈：

```python
# 尝试从数据库或外部源恢复缺失的蜡烛
recovered = await self._recover_gap_candles(
    series_id=series_id,
    expected_next_time=int(expected_next),
    actual_time=first_time,
)
if recovered:
    sendable = self._merge_candles([*recovered, *sendable])
```

- 补回来了 → 把补回的蜡烛和原数据合并，前端完全无感。
- 补不回来 → 发送 gap 消息，明确告诉前端"这里有断层"。

```python
# gap 消息格式
{
    "type": "gap",
    "series_id": "BTCUSDT:1h",
    "expected_next_time": 280,
    "actual_time": 400,
}
```

就像追剧平台：发现你少了 6、7、8 集，先尝试帮你找到这三集。找到了就自动补上；找不到就弹个提示"第 6~8 集暂时缺失"。

### 6.3 前端收到 gap 怎么办

前端收到 gap 消息后，会主动发 HTTP 请求去补数据：

```typescript
if (msg.type === "gap") {
    // 计算缺失范围
    const since = msg.expected_next_time - timeframeSeconds;

    // 用 HTTP 接口补数据
    void fetchCandles({ seriesId, since, limit: 5000 }).then(({ candles }) => {
        if (candles.length === 0) return;
        setCandles((prev) => mergeCandlesWindow(prev, candles, INITIAL_TAIL_LIMIT));
    });

    // 重置覆盖层状态（因为数据可能不连续了）
    overlayCursorVersionRef.current = 0;
}
```

这是"WS 通知 + HTTP 补偿"的协作模式：WS 负责告诉你"哪里有洞"，HTTP 负责"把洞补上"。

---

## 7. Batch vs Stream：同语义，不同传输形态

订阅时客户端可以声明 `supports_batch: true`。

### Batch 模式

catchup 时把所有历史蜡烛打包成一条 `candles_batch` 消息发送：

```json
{
    "type": "candles_batch",
    "series_id": "BTCUSDT:1h",
    "candles": [
        {"candle_time": 160, "open": 100, ...},
        {"candle_time": 220, "open": 101, ...}
    ]
}
```

好处：一次网络往返传 50 根蜡烛，比发 50 条消息高效得多。

### Stream 模式

catchup 时逐根发送 `candle_closed` 消息。

两种模式的关键：**语义完全一致。** 同样的去重规则、同样的 gap 检测、同样的 last_sent_time 更新。只是网络传输形态不同。

就像寄快递：你可以一个包裹寄 50 本书（batch），也可以寄 50 个包裹每个一本书（stream）。书是一样的，只是打包方式不同。

---

## 8. Forming 消息：实时预览，但不破坏时序

forming 是"正在形成的蜡烛"——这根蜡烛还没收盘，价格还在变。

### 8.1 节流：不是每次价格变动都推

```python
forming_min_interval_ms = 250  # 最小间隔 250ms

if (candle.candle_time != last_forming_candle_time
    or (now - last_forming_emit_at) >= forming_min_interval_s):
    await hub.publish_forming(series_id=series_id, candle=candle)
```

Binance 每秒可能推几十次价格更新。如果每次都转发给前端，前端会被刷屏。所以系统做了 250ms 节流：同一根蜡烛的 forming 更新，至少间隔 250ms 才推一次。

就像股票行情软件：价格每毫秒都在变，但屏幕上的数字不会每毫秒刷新一次，而是每隔一小段时间刷新一次。

### 8.2 不破坏 closed 序列

forming 有一个铁律：**不更新 last_sent_time。**

```python
# Hub 发送 forming 时
if sub.last_sent_time is not None and candle.candle_time <= sub.last_sent_time:
    continue  # 跳过已发送过的
# 注意：发送后不更新 sub.last_sent_time
```

为什么？因为 `last_sent_time` 是 closed 序列的进度条。如果 forming 也更新它，那当这根蜡烛真正 close 时，就会被 `_should_skip_candle` 跳过——closed 蜡烛反而丢了。

就像考试的草稿纸：你在草稿纸上写的答案（forming）不算数，只有写在答题卡上的（closed）才算。进度条只跟踪答题卡。

---

## 9. 竞态防护：catchup 和 live 同时到来怎么办

经典竞态场景：

1. 客户端发送 subscribe(since=100)；
2. 服务器开始读历史数据（catchup）；
3. 同时，新蜡烛 280 到达，Hub 尝试推送给这个客户端；
4. catchup 读完了，包含 160 和 220。

如果没有防护，280 可能在 catchup 之前就被推送了，导致前端收到的顺序是 280 → 160 → 220，完全乱序。

系统的防线是双重的：

1. **catchup 阶段**：基于 `effective_since` 过滤，只发 `> effective_since` 的蜡烛。
2. **live 阶段**：Hub 发送前用 `_should_skip_candle` 检查，只发 `> last_sent_time` 的蜡烛。

因为 catchup 完成后会更新 `last_sent_time = 220`，所以即使 280 在 catchup 期间被推送了，catchup 结束后 live 推送 280 时也不会重复（因为 280 > 220）。

就像电影院的进度条：不管回放和直播怎么交叉，进度条只往前走，已经播过的不会再播。

---

## 10. 容量拒绝：不是偷偷降级，而是明确说"不行"

当服务器的按需摄取作业达到上限时：

```json
{
    "type": "error",
    "code": "capacity",
    "message": "ondemand_ingest_capacity",
    "series_id": "ETHUSDT:5m"
}
```

关键：被拒绝的 series 不会收到任何数据帧——不会有 catchup，不会有 live，不会有 forming。

为什么这么严格？因为"一边报错一边夹杂数据"是最危险的状态。前端不知道该信错误还是该信数据，状态机会混乱。

就像餐厅满座：要么明确告诉你"没位子了"，要么给你安排座位。不能说"没位子了"然后偷偷给你上一盘菜。

---

## 11. 前端蜡烛合并：乱序容错的最后一道防线

前端收到蜡烛后，用一个简单但有效的合并策略：

```typescript
function mergeCandle(list: Candle[], next: Candle): Candle[] {
    const last = list[list.length - 1];
    if (!last) return [next];
    if (next.time === last.time) return [...list.slice(0, -1), next]; // 替换（forming → closed）
    if (next.time > last.time) return [...list, next];                // 追加
    return list;                                                       // 忽略乱序
}
```

三条规则：
- 时间相同 → 替换（forming 被 closed 覆盖）；
- 时间更大 → 追加（正常推进）；
- 时间更小 → 忽略（乱序丢弃）。

这是前端的最后一道防线：即使后端的去重机制有漏洞，前端也不会因为乱序数据而崩溃。

---

## 12. 完整时序图：一个订阅的一生

```text
客户端                              服务器
  |                                   |
  |--- subscribe(since=100) -------->|
  |                                   |
  |                            [读历史: 160, 220]
  |                            [effective_since = max(100, null) = 100]
  |                            [无 gap]
  |                            [更新 last_sent = 220]
  |                                   |
  |<--- candles_batch [160,220] -----|
  |                                   |
  |<--- candle_forming(280, $42100) -|  ← 250ms 节流
  |<--- candle_forming(280, $42150) -|
  |                                   |
  |<--- candle_closed(280) ----------|  ← last_sent 更新为 280
  |                                   |
  |          ... 网络抖动，340 丢失 ...
  |                                   |
  |                            [expected_next = 340]
  |                            [actual = 400]
  |                            [尝试回补 340 → 成功]
  |                                   |
  |<--- candle_closed(340) ----------|  ← 回补的
  |<--- candle_closed(400) ----------|  ← 实时的
  |                                   |
  |          ... 如果回补失败 ...
  |                                   |
  |<--- gap(expected=340, actual=400)|
  |                                   |
  |--- HTTP fetchCandles(since=280)->|  ← 前端主动补数据
  |<--- [340, 400] ------------------|
```

---

## 13. 这套设计背后的四条工程原则

```text
原则1：Single monotonic cursor per connection（每连接一个单调游标）
  → last_sent_time 只增不减，是所有去重的基石
  → 就像电影进度条，只往前走

原则2：Catchup/live same gate（历史和实时过同一道门）
  → 不管数据来自历史补发还是实时推送，都用 last_sent_time 过滤
  → 就像安检门，不管你是 VIP 还是普通旅客，都要过

原则3：Gap is first-class message（间隙是一等公民）
  → gap 不是日志里的一行警告，而是协议里的正式消息
  → 前端可以据此做确定性的补偿动作

原则4：Degrade explicitly（降级要明确）
  → 容量不足时明确拒绝，不给半状态
  → 就像餐厅满座要明确告知，不能一边说没位子一边上菜
```

---

## 14. 代码锚点（按链路读）

| 概念 | 文件 | 干什么的 |
| ---- | ---- | ---- |
| WS 协议定义 | `backend/app/ws_protocol.py` | 消息类型枚举 + 错误码 |
| WS 路由 | `backend/app/market_ws_routes.py` | WebSocket 端点 + 消息分发 |
| 订阅协调器 | `backend/app/market_data/ws_services.py` | catchup 流程编排 |
| CandleHub | `backend/app/ws_hub.py` | last_sent_time + gap 检测 + 发送 |
| 前端 WS 解析 | `frontend/src/widgets/chart/ws.ts` | 消息类型定义 + 解析 |
| 前端蜡烛合并 | `frontend/src/widgets/chart/candles.ts` | mergeCandle 乱序容错 |
| 前端图表组件 | `frontend/src/widgets/ChartView.tsx` | 订阅 + 消息处理 + gap 补偿 |
| WS 测试 | `backend/tests/test_market_ws.py` | catchup/batch/gap 场景 |
| Hub 投递测试 | `backend/tests/test_ws_hub_delivery.py` | 去重/竞态/forming 场景 |

---

## 15. 过关自测

1. 为什么 `effective_since` 要取 `max(since, last_sent_time)`？如果只用 `since` 会怎样？
2. gap 消息在协议里承担什么角色？为什么不能只打日志而不通知前端？
3. forming 为什么不更新 `last_sent_time`？如果更新了会导致什么问题？
4. catchup 和 live 竞态时，系统靠哪两层机制避免重复发送？
5. 前端的 `mergeCandle` 为什么要忽略时间更小的蜡烛？这是在防什么？

能把这 5 题讲清楚，你就掌握了实时推送系统里最核心的难题——"迟到观众"怎么无缝接上直播。
