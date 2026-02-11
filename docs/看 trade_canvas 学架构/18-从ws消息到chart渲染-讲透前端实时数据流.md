---
title: 第18关：从 WS 消息到 Chart 渲染，讲透前端实时数据流
status: done
created: 2026-02-11
updated: 2026-02-11
---

# 第18关：从 WS 消息到 Chart 渲染，讲透前端实时数据流

上一关你学了"数据放哪"。这一关解决"数据怎么流"。

trade_canvas 的前端不是一个静态页面。它是一个实时系统——K线在跳、因子在算、覆盖层在画。每秒钟都有新数据从后端涌进来，前端必须把这些数据变成画面。

这就像一个电视台的导播室。信号从卫星（WS）和光纤（HTTP）两条线路进来，导播（ChartView）要把它们合成一个画面，实时播出。

问题是：

- 两条线路的数据到达顺序不确定。
- 有时候信号会中断（gap）。
- 有时候你不是看直播，而是看录像（replay）。

怎么保证画面始终正确？

---

## 1. 两种模式，两条数据流

trade_canvas 的图表有两种模式：

```text
Live 模式（看直播）：
  WS 推送 K线 → 合并到内存 → 触发覆盖层轮询 → 更新画面

Replay 模式（看录像）：
  用户拖进度条 → 从回放包取窗口 → 重建因子+覆盖层 → 更新画面
```

两种模式共享同一个图表组件（ChartView），但数据来源完全不同。

就像电视机：你可以看直播频道，也可以看录像回放。屏幕是同一块，但信号源不同。

---

## 2. Live 模式：从 WS 消息到画面的完整链路

### 2.1 第一步：建立连接，加载初始数据

```typescript
// frontend/src/widgets/ChartView.tsx（简化版）
async function run() {
  // 1. HTTP 加载最近 2000 根 K线
  const initial = await fetchCandles({ seriesId, limit: 2000 });
  setCandles(initial.candles);
  cursor = initial.candles[initial.candles.length - 1]?.time ?? 0;

  // 2. 加载初始覆盖层（世界帧模式）
  const frame = await fetchWorldFrameLive({ seriesId, windowCandles: 2000 });
  applyWorldFrame(frame);

  // 3. 建立 WS 连接
  const ws = new WebSocket(`${apiWsBase()}/ws/market`);
  ws.onopen = () => {
    ws.send(JSON.stringify({
      type: "subscribe",
      series_id: seriesId,
      since: cursor > 0 ? cursor : null,
      supports_batch: true,
    }));
  };
}
```

注意三步的顺序：先 HTTP 拉历史，再 HTTP 拉覆盖层，最后才开 WS。

为什么？因为 WS 是增量流，你必须先有"全量底图"，增量才有意义。就像看球赛直播——你得先知道比分是 2:1，才能理解"又进了一球"意味着 3:1。

### 2.2 第二步：处理 WS 消息

WS 连接建立后，后端会推送六种消息：

```typescript
// frontend/src/widgets/chart/ws.ts
export type MarketWsMessage =
  | { type: "candle_forming"; candle: CandleClosed }  // 正在形成的 K线
  | { type: "candle_closed"; candle: CandleClosed }   // 已闭合的 K线
  | { type: "candles_batch"; candles: CandleClosed[] } // 批量补发
  | MarketWsGap                                        // 时序断裂
  | MarketWsError                                      // 错误
  | MarketWsSystem;                                    // 系统事件
```

六种消息就像六种快递：

- `candle_forming`：预览件，随时会被替换（就像外卖 App 上"骑手已出发"）。
- `candle_closed`：正式件，盖了章的（"已签收"）。
- `candles_batch`：补发包裹，一次来好几个。
- `gap`：快递丢了，需要补寄。
- `error`：快递站出故障了。
- `system`：快递站发通知（比如"因子已重算"）。

每种消息的处理逻辑不同：

```typescript
// ChartView.tsx（简化版）
ws.onmessage = (evt) => {
  const msg = parseMarketWsMessage(evt.data);
  if (!msg) return;

  if (msg.type === "candle_forming") {
    // 直接合并，不触发覆盖层更新
    setCandles(prev => mergeCandleWindow(prev, toChartCandle(msg.candle), 2000));
  }

  if (msg.type === "candle_closed") {
    // 合并 + 触发覆盖层跟随
    setCandles(prev => mergeCandleWindow(prev, toChartCandle(msg.candle), 2000));
    scheduleOverlayFollow(msg.candle.candle_time);
  }

  if (msg.type === "candles_batch") {
    // 批量合并 + 触发覆盖层跟随
    setCandles(prev => mergeCandlesWindow(prev, batch.map(toChartCandle), 2000));
    scheduleOverlayFollow(lastTime);
  }
};
```

关键区别：`candle_forming` 不触发 `scheduleOverlayFollow`，`candle_closed` 和 `candles_batch` 才触发。

为什么？因为 forming 是"草稿"，随时会变。你不会因为骑手换了条路就重新算送达时间——等他真到了再说。

### 2.3 第三步：Gap 处理——信号中断怎么办

Gap 是最复杂的消息。它意味着"中间有 K线丢了"。

```text
正常序列：  K1 → K2 → K3 → K4 → K5
Gap 场景：  K1 → K2 → [gap] → K5
                      ↑ K3、K4 丢了
```

处理策略是"HTTP 补 + 状态重置"：

```typescript
// ChartView.tsx gap 处理（简化版）
if (msg.type === "gap") {
  // 1. 用 HTTP 补回缺失的 K线
  const chunk = await fetchCandles({ seriesId, since: gapSince, limit: 5000 });
  setCandles(prev => mergeCandlesWindow(prev, chunk, 2000));

  // 2. 重置所有覆盖层状态
  overlayCatalogRef.current.clear();
  overlayActiveIdsRef.current.clear();
  overlayCursorVersionRef.current = 0;

  // 3. 重新加载覆盖层（世界帧优先）
  if (worldFrameHealthy) {
    const frame = await loadWorldFrameLive();
    applyWorldFrame(frame);
  } else {
    const delta = await fetchOverlayLikeDelta({ cursorVersionId: 0 });
    applyOverlayDelta(delta);
  }
}
```

为什么要重置覆盖层？因为 gap 意味着中间可能有 `candle_closed` 事件丢失，后端的因子链路已经跑过了，但前端的覆盖层游标还停在旧位置。与其猜"丢了几步"，不如从零重建。

就像考试漏了几道题——与其猜答案，不如重新做一遍。

---

## 3. 覆盖层跟随：不是每根 K线都拉，而是防抖

K线可能每秒更新好几次（forming），但覆盖层不需要这么频繁。trade_canvas 用了一个 1 秒防抖：

```typescript
const FOLLOW_DEBOUNCE_MS = 1000;

function scheduleOverlayFollow(t: number) {
  // 记录最新时间（取 max，保证不回退）
  followPendingTimeRef.current = Math.max(followPendingTimeRef.current ?? 0, t);
  // 如果已有定时器在跑，不重复设
  if (followTimerIdRef.current != null) return;
  // 如果正在拉取中，也不设（等拉完再调度）
  if (overlayPullInFlightRef.current) return;

  followTimerIdRef.current = window.setTimeout(() => {
    followTimerIdRef.current = null;
    const next = followPendingTimeRef.current;
    followPendingTimeRef.current = null;
    if (next != null) runOverlayFollowNow(next);
  }, FOLLOW_DEBOUNCE_MS);
}
```

这就像电梯的"关门延迟"：有人按了楼层，电梯不会立刻关门，而是等 1 秒看还有没有人进来。如果 1 秒内又有人按了，就更新目标楼层，但不重新计时。

三重保护：

1. **防抖**：1 秒内多次 closed，只拉一次。
2. **去重**：`overlayPullInFlightRef` 保证同时只有一个请求在飞。
3. **不回退**：`Math.max` 保证时间只往前走。

---

## 4. 世界帧优先，Delta 兜底

覆盖层拉取有两条路径：

```text
路径 A（世界帧 World Frame）：
  pollWorldDelta → 返回 draw_delta + factor_slices → 一次搞定

路径 B（传统 Delta）：
  fetchOverlayLikeDelta → 只返回 draw 变更 → 还需单独拉 factor
```

代码里的选择逻辑：

```typescript
function runOverlayFollowNow(t: number) {
  if (ENABLE_WORLD_FRAME && worldFrameHealthyRef.current) {
    // 路径 A：世界帧
    pollWorldDelta({ seriesId, afterId, windowCandles: 2000 })
      .then(resp => { applyOverlayDelta(resp); applyFactorSlices(resp); })
      .catch(() => { worldFrameHealthyRef.current = false; })  // 降级！
  } else {
    // 路径 B：传统 Delta（兜底）
    fetchOverlayLikeDelta({ seriesId, cursorVersionId: cur })
      .then(delta => applyOverlayDelta(delta));
  }
}
```

注意 `.catch` 里的 `worldFrameHealthyRef.current = false`——一旦世界帧出错，自动降级到传统 Delta，不会反复重试失败路径。

这就像导航 App：优先走高速（世界帧），如果高速封了（报错），自动切国道（Delta），不会傻等高速开通。

---

## 5. K线合并：三条规则，一个窗口

K线合并是前端数据流的基础操作。`mergeCandle` 只有三条规则：

```typescript
// frontend/src/widgets/chart/candles.ts
export function mergeCandle(list: Candle[], next: Candle): Candle[] {
  const last = list[list.length - 1];
  if (!last) return [next];                              // 空列表，直接放
  if (next.time === last.time) return [...list.slice(0, -1), next]; // 同时间，替换
  if (next.time > last.time) return [...list, next];     // 更新，追加
  return list;                                           // 更旧，忽略
}
```

三条规则对应三种场景：

| 规则 | 场景 | 比喻 |
| ------ | ------ | ------ |
| 同时间替换 | forming 更新当前 K线 | 黑板上擦掉重写 |
| 更新追加 | closed 新增一根 K线 | 黑板上往后写一行 |
| 更旧忽略 | 迟到的旧消息 | 已经翻页了，不回头 |

`mergeCandleWindow` 在 `mergeCandle` 基础上加了窗口限制：

```typescript
export function mergeCandleWindow(list: Candle[], next: Candle, limit: number): Candle[] {
  const merged = mergeCandle(list, next);
  if (limit > 0 && merged.length > limit) return merged.slice(-limit);
  return merged;
}
```

`limit = 2000`（`INITIAL_TAIL_LIMIT`），超过就从头部裁掉。就像一个固定长度的传送带——新货从右边上，左边的自动掉下去。

---

## 6. Replay 模式：进度条驱动一切

Replay 模式的数据流和 Live 完全不同。没有 WS，没有实时推送，一切由 `replayIndex`（进度条位置）驱动：

```typescript
// ChartView.tsx（简化版）
useEffect(() => {
  if (!replayEnabled) return;
  const all = replayAllCandlesRef.current;
  if (all.length === 0) return;

  const clamped = Math.max(0, Math.min(replayIndex, replayTotal - 1));
  const time = all[clamped].time;

  // 1. 设置焦点时间
  setReplayFocusTime(time);
  // 2. 按时间重建覆盖层
  applyReplayOverlayAtTime(time);
  // 3. 拉取因子高亮
  fetchAndApplyAnchorHighlightAtTime(time);
  // 4. 请求回放帧
  requestReplayFrameAtTime(time);
}, [replayIndex, replayTotal, replayEnabled]);
```

就像视频播放器：你拖进度条到某个位置，播放器就渲染那一帧的画面。不需要从头播到那里，直接跳转。

自动播放也很简单——一个定时器不断递增 `replayIndex`：

```typescript
useEffect(() => {
  if (!replayEnabled || !replayPlaying) return;
  if (replayIndex >= replayTotal - 1) return;  // 到头了

  const id = window.setTimeout(() => {
    setReplayIndexAndFocus(replayIndex + 1);
  }, replaySpeedMs);  // 播放速度（毫秒/帧）

  return () => window.clearTimeout(id);
}, [replayIndex, replayPlaying, replaySpeedMs]);
```

每次 `replayIndex` 变化，上面的 `useEffect` 就会触发，重建那一帧的所有数据。就像翻书动画——每翻一页就画一帧，翻得快就是快进。

---

## 7. 完整数据流图

把所有环节串起来：

```text
=== Live 模式 ===

HTTP 初始加载                    WS 实时推送
     │                              │
     ▼                              ▼
fetchCandles(2000)          parseMarketWsMessage
     │                         ┌────┼────┐
     ▼                         ▼    ▼    ▼
setCandles ◄── mergeCandle ── forming closed gap
     │                              │     │
     │                              ▼     ▼
     │                    scheduleOverlay  HTTP补K
     │                     (1s 防抖)      + 状态重置
     │                         │
     ▼                         ▼
  ┌──────────────────────────────────┐
  │  runOverlayFollowNow             │
  │  ┌─ 世界帧优先 ──► applyWorld   │
  │  └─ Delta 兜底 ──► applyDelta   │
  └──────────────────────────────────┘
                    │
                    ▼
            rebuildMarkers
            rebuildPenPoints
            syncMarkers
                    │
                    ▼
              Chart 渲染

=== Replay 模式 ===

用户拖进度条 / 自动播放定时器
          │
          ▼
    replayIndex 变化
          │
    ┌─────┼──────────┐
    ▼     ▼          ▼
 setFocus applyOverlay fetchAnchor
    │     AtTime      Highlight
    │        │            │
    └────────┼────────────┘
             ▼
       Chart 渲染
```

---

## 8. 这套设计背后的工程范式

### 8.1 "先全量后增量"模式

HTTP 拉全量 → WS 接增量。这是实时系统的经典模式。全量是地基，增量是砖块。没有地基，砖块没地方放。

### 8.2 "forming 不入账"原则

forming 只更新画面，不触发因子/覆盖层计算。这和后端的"forming 不落库"一脉相承——草稿就是草稿，不能当正式文件用。

### 8.3 "降级而非重试"策略

世界帧失败 → 自动切 Delta，不反复重试。这比"重试 3 次再报错"更优雅——用户感知不到切换，系统继续工作。

### 8.4 "防抖 + 去重 + 不回退"三重保护

覆盖层轮询不是"来一根拉一次"，而是用防抖合并、用 inFlight 去重、用 Math.max 防回退。三层保护让高频场景下的网络请求可控。

### 8.5 "同组件双模式"复用

Live 和 Replay 共享 ChartView，通过 `replayEnabled` 开关切换数据源。组件不关心数据从哪来，只关心"给我 candles 和 overlays，我来画"。

---

## 9. 代码锚点（按数据流顺序阅读）

| 文件 | 职责 |
| ------ | ------ |
| `frontend/src/lib/api.ts` | `apiUrl` / `apiWsBase` 地址构建 |
| `frontend/src/widgets/chart/ws.ts` | WS 消息类型定义 + `parseMarketWsMessage` |
| `frontend/src/widgets/chart/candles.ts` | `mergeCandle` / `mergeCandleWindow` / `mergeCandlesWindow` |
| `frontend/src/widgets/ChartView.tsx:2324` | WS 连接建立 + subscribe |
| `frontend/src/widgets/ChartView.tsx:2342` | `scheduleOverlayFollow` 防抖调度 |
| `frontend/src/widgets/ChartView.tsx:2356` | `runOverlayFollowNow` 世界帧优先 + Delta 兜底 |
| `frontend/src/widgets/ChartView.tsx:2432` | `ws.onmessage` 六种消息分发 |
| `frontend/src/widgets/ChartView.tsx:2507` | Gap 处理：HTTP 补 K + 状态重置 |
| `frontend/src/widgets/ChartView.tsx:2772` | Replay 模式：replayIndex 驱动渲染 |
| `frontend/src/widgets/ChartView.tsx:2799` | Replay 自动播放定时器 |

---

## 10. 过关自测

1. 为什么 WS 连接必须在 HTTP 初始加载之后建立，而不是同时？
2. `candle_forming` 和 `candle_closed` 的处理有什么关键区别？为什么这样设计？
3. Gap 消息为什么要重置覆盖层状态到 0，而不是尝试增量补齐？
4. `scheduleOverlayFollow` 的三重保护分别解决什么问题？
5. Live 模式和 Replay 模式共享 ChartView 的好处是什么？如果分成两个组件会有什么问题？

如果你能把这 5 题讲清楚，你就理解了"实时前端不是简单的 WS 推啥画啥"，而是一套有降级、有防抖、有模式切换的完整数据流架构。
