---
title: 第19关：从 Lightweight Charts 到绘图工具，讲透图表渲染架构
status: done
created: 2026-02-11
updated: 2026-02-11
---

# 第19关：从 Lightweight Charts 到绘图工具，讲透图表渲染架构

上一关你学了"数据怎么流"。这一关解决"数据怎么画"。

trade_canvas 的图表不是一张静态图片。它是一个多层画布——K线在底层、笔和中枢在中间、绘图工具在顶层。每一层有自己的数据源、更新频率和渲染方式。

这就像一个画家的工作台。画布（Lightweight Charts）是底座，油画颜料（K线 Series）画主体，水彩（Overlay Series）画叠加层，最后用铅笔（绘图工具）做标注。每种材料的特性不同，但最终合成一幅画。

问题是：

- 怎么让多层数据各自更新，互不干扰？
- 怎么把后端的"指令目录"变成屏幕上的线条和标记？
- 怎么让用户的手动绘图和自动覆盖层共存？

---

## 1. 图表初始化：一个 Hook 搞定

trade_canvas 把图表初始化封装在 `useLightweightChart` 这个 Hook 里：

```typescript
// frontend/src/widgets/chart/useLightweightChart.ts（简化版）
const chart = createChart(container, {
  layout: {
    background: { color: "#0b0f14" },
    textColor: "#c9d1d9"
  },
  grid: {
    vertLines: { color: "rgba(255,255,255,0.05)" },
    horzLines: { color: "rgba(255,255,255,0.05)" }
  },
  crosshair: { mode: 0, horzLine: { labelVisible: false } },
  handleScroll: { mouseWheel: false, pressedMouseMove: true },
  handleScale: { mouseWheel: false, pinch: true },
});

// 创建 K线 Series
const series = chart.addSeries(CandlestickSeries, {
  upColor: "#22c55e", downColor: "#ef4444",
  wickUpColor: "#22c55e", wickDownColor: "#ef4444",
  borderVisible: false,
});

// 创建 Markers 插件
const markersApi = createSeriesMarkers(series);
```

注意两个"关闭"：`mouseWheel: false`（滚轮不缩放）和 `handleScale.mouseWheel: false`。为什么？因为图表嵌在可滚动的页面里，滚轮要留给页面滚动，缩放用 Ctrl+滚轮 或双指捏合。

就像嵌在网页里的 Google Maps——默认滚轮是翻页，按住 Ctrl 才是缩放地图。

这个 Hook 返回三样东西：`chart`（图表实例）、`series`（K线 Series）、`markersApi`（标记插件）。整个 ChartView 的渲染都建立在这三样东西之上。

---

## 2. 多层 Series：每种数据一条线

Lightweight Charts 的核心概念是 Series——每种数据用一个独立的 Series 渲染。trade_canvas 用了这些 Series：

```text
┌─────────────────────────────────────────────┐
│                 Chart 画布                    │
│                                              │
│  CandlestickSeries ─── K线（底层）            │
│  LineSeries × N ────── SMA 均线               │
│  LineSeries ────────── 笔（pen.confirmed）    │
│  LineSeries × N ────── 覆盖层多边形            │
│  LineSeries ────────── 锚点笔                 │
│  LineSeries × 2 ────── 回放预览笔              │
│  Markers ───────────── 枢轴点 / 锚点切换标记   │
│  Canvas ────────────── 中枢矩形 / 锚点顶层     │
│                                              │
└─────────────────────────────────────────────┘
```

每个 Series 都用 Ref 管理生命周期：

```typescript
// ChartView.tsx
const lineSeriesByKeyRef = useRef<Map<string, ISeriesApi<"Line">>>(new Map());  // SMA
const penSeriesRef = useRef<ISeriesApi<"Line"> | null>(null);                   // 笔
const overlayPolylineSeriesByIdRef = useRef<Map<string, ISeriesApi<"Line">>>(new Map()); // 覆盖层
const anchorPenSeriesRef = useRef<ISeriesApi<"Line"> | null>(null);             // 锚点笔
```

为什么用 Map 管理？因为覆盖层的 polyline 数量是动态的——中枢可能有 3 个也可能有 30 个。Map 的 key 是 overlay id，value 是对应的 LineSeries。

就像一个画架上的颜料盘：K线是固定的一管红绿，但覆盖层的颜色随时在加减。Map 让你随时"挤一管新颜料"或"扔掉用完的"。

---

## 3. 从 Overlay Catalog 到屏幕像素

上一关讲了覆盖层数据怎么从后端流到前端。这一关讲它怎么变成画面。

核心流程是三个 `rebuild` 函数：

```text
Overlay Catalog (内存中的指令目录)
       │
       ├── rebuildPivotMarkersFromOverlay()  → Markers（点标记）
       ├── rebuildPenPointsFromOverlay()     → LineSeries（笔折线）
       └── rebuildOverlayPolylinesFromOverlay() → LineSeries × N（中枢/锚点等）
       │
       └── syncMarkers()  → 合并所有 Markers，一次性提交
```

### 3.1 Pivot Markers：从目录到标记点

```typescript
// ChartView.tsx rebuildPivotMarkersFromOverlay（简化版）
function rebuildPivotMarkersFromOverlay() {
  const next = [];
  for (const id of overlayActiveIdsRef.current) {
    const item = overlayCatalogRef.current.get(id);
    if (!item || item.kind !== "marker") continue;

    const def = item.definition;
    const feature = def.feature;  // "pivot.major" 或 "pivot.minor"
    if (!effectiveVisible(feature)) continue;

    // 样式规范化：minor 比 major 小
    const shape = feature === "pivot.minor" ? "circle" : def.shape;
    const size = feature === "pivot.minor" ? 0.5 : 1.0;

    next.push({ time: def.time, position: def.position, color: def.color, shape, size });
  }
  next.sort((a, b) => a.time - b.time);  // Lightweight Charts 要求时间升序
  pivotMarkersRef.current = next;
}
```

注意最后的 `sort`——Lightweight Charts 要求 markers 严格按时间升序排列，否则会渲染异常。就像排队进场，不按号码顺序就会乱套。

### 3.2 Pen Points：从目录到折线

```typescript
function rebuildPenPointsFromOverlay() {
  const item = overlayCatalogRef.current.get("pen.confirmed");
  if (!item || item.kind !== "polyline") { penPointsRef.current = []; return; }

  const points = item.definition.points;
  const out = [];
  for (const p of points) {
    const t = p.time, v = p.value;
    // 只保留当前 K线窗口范围内的点
    if (t < minTime || t > maxTime) continue;
    out.push({ time: t, value: v });
  }
  penPointsRef.current = out;
}
```

笔只有一条（`pen.confirmed`），所以直接用固定 id 查找。不像 pivot 那样要遍历所有 active ids。

### 3.3 Overlay Polylines：动态创建和销毁 Series

这是最复杂的部分。因为中枢、锚点等覆盖层的数量是动态的：

```typescript
function rebuildOverlayPolylinesFromOverlay() {
  // 1. 收集所有需要的 polyline
  const want = new Map();  // id → { points, color, lineWidth, lineStyle }
  for (const id of overlayActiveIdsRef.current) {
    if (id === "pen.confirmed") continue;  // 笔单独处理
    const item = overlayCatalogRef.current.get(id);
    if (!item || item.kind !== "polyline") continue;
    if (!effectiveVisible(item.definition.feature)) continue;
    want.set(id, { points, color, lineWidth, lineStyle });
  }

  // 2. 删除不再需要的 Series
  for (const [id, series] of overlayPolylineSeriesByIdRef.current) {
    if (!want.has(id)) {
      chart.removeSeries(series);
      overlayPolylineSeriesByIdRef.current.delete(id);
    }
  }

  // 3. 创建或更新需要的 Series
  for (const [id, item] of want) {
    let series = overlayPolylineSeriesByIdRef.current.get(id);
    if (!series) {
      series = chart.addSeries(LineSeries, { color: item.color, ... });
      overlayPolylineSeriesByIdRef.current.set(id, series);
    }
    series.setData(item.points);
  }
}
```

这是一个经典的"声明式同步"模式：

1. 先算出"应该有什么"（want）。
2. 删掉"有但不该有的"。
3. 创建"该有但没有的"，更新"已有的"。

就像布置展厅：先列出展品清单，再撤掉不在清单上的，最后摆上新的。不是每次都清空重来，而是增量调整。

---

## 4. Marker 合并：三源归一

图表上的标记点来自三个来源：

```typescript
// ChartView.tsx
const pivotMarkersRef = useRef([]);        // 枢轴点（来自 overlay）
const anchorSwitchMarkersRef = useRef([]); // 锚点切换（来自 overlay）
const entryMarkersRef = useRef([]);        // 入场信号（来自回测）
```

但 Lightweight Charts 的 Markers API 只接受一个数组。所以需要合并：

```typescript
const syncMarkers = useCallback(() => {
  const markers = [
    ...pivotMarkersRef.current,
    ...anchorSwitchMarkersRef.current,
    ...entryMarkersRef.current,
  ];
  markersApiRef.current?.setMarkers(markers);
}, []);
```

为什么不是每种 marker 单独一个 API？因为 Lightweight Charts 的 markers 是绑定在 Series 上的，一个 Series 只有一个 markers 列表。所以必须合并后一次性提交。

就像一块公告板——你不能给每个部门各一块板，只能把所有通知贴在同一块板上。

---

## 5. Canvas 层：Lightweight Charts 画不了的，自己画

有些图形 Lightweight Charts 的 Series 和 Markers 画不了——比如中枢的矩形区域、锚点的顶层高亮线。这时候就需要原生 Canvas。

trade_canvas 在图表上叠了两层 Canvas：

```text
┌──────────────────────────┐
│  Canvas 2: 锚点顶层线条   │  ← 最上层
├──────────────────────────┤
│  Canvas 1: 中枢矩形       │
├──────────────────────────┤
│  Lightweight Charts       │  ← 底层（K线 + Series + Markers）
└──────────────────────────┘
```

Canvas 绘制的数据同样来自 Overlay Catalog，但渲染方式不同——不是调用 `series.setData()`，而是直接用 Canvas 2D API 画矩形和线条。

为什么要分两层 Canvas？因为锚点线条需要画在中枢矩形之上。如果只有一层，就要手动控制绘制顺序。分层后，浏览器的 z-index 自动处理遮挡关系。

就像 Photoshop 的图层——底层画背景，中间画主体，顶层画高光。每层独立编辑，合成时自动叠加。

---

## 6. 绘图工具：用户的铅笔

除了自动生成的覆盖层，trade_canvas 还提供手动绘图工具：

### 6.1 三种工具

```text
PositionTool ── 仓位工具（入场价 + 止损 + 止盈）
FibTool ─────── 斐波那契回撤（两点定义 + 自动算比例线）
MeasureTool ─── 测量工具（价差 + 时间差 + K线数）
```

### 6.2 统一接口

三种工具共享相同的 Props 接口：

```typescript
{
  chartRef,          // 图表实例
  seriesRef,         // K线 Series（用于坐标转换）
  containerRef,      // 容器 DOM（用于鼠标事件）
  candleTimesSec,    // K线时间数组（用于吸附到最近 K线）
  tool,              // 工具实例数据
  isActive,          // 是否激活
  interactive,       // 是否可交互
  onUpdate,          // 更新回调
  onRemove,          // 删除回调
  onSelect,          // 选中回调
  onInteractionLockChange,  // 交互锁（拖拽时锁住图表滚动）
}
```

这个统一接口让 ChartView 可以用同一套逻辑管理所有绘图工具，不需要为每种工具写特殊处理。

### 6.3 坐标转换：从像素到价格

绘图工具的核心难题是坐标转换——用户点击的是屏幕像素，但工具需要的是"时间 + 价格"：

```typescript
// frontend/src/widgets/chart/draw_tools/chartCoord.ts
function resolveTimeFromX({ chart, x, candleTimesSec }) {
  // 像素 x → 逻辑坐标 → 吸附到最近的 K线时间
}

// Lightweight Charts 内置的坐标转换
const price = series.coordinateToPrice(y);  // 像素 y → 价格
```

时间轴的转换比价格轴复杂，因为要"吸附"到最近的 K线。你不能在两根 K线之间画标记——就像你不能在日历的两天之间标注事件。

### 6.4 Fib 预览：requestAnimationFrame 的正确用法

斐波那契工具有一个实时预览功能——鼠标移动时，回撤线跟着动。这需要高频更新，但不能每次 mousemove 都重绘：

```typescript
// frontend/src/widgets/chart/draw_tools/useFibPreview.ts（简化版）
const onMove = (e: PointerEvent) => {
  lastMouseRef.current = { x: e.clientX - rect.left, y: e.clientY - rect.top };
  schedule();  // 不直接更新，而是调度
};

function schedule() {
  if (rafIdRef.current != null) return;  // 已有帧在等，不重复
  rafIdRef.current = requestAnimationFrame(() => {
    rafIdRef.current = null;
    // 在这里做坐标转换 + 更新预览
    const time = resolveTimeFromX({ chart, x: mouse.x, candleTimesSec });
    const price = series.coordinateToPrice(mouse.y);
    setPreviewTool({ anchors: { a: anchorA, b: { time, price } } });
  });
}
```

`requestAnimationFrame` 保证每帧最多更新一次（约 60fps）。鼠标可能每秒触发几百次 mousemove，但实际重绘只有 60 次。

就像电影胶片——摄像机每秒拍 24 帧，不管演员动了多少次。多余的动作在两帧之间，观众看不到。

---

## 7. 滚轮与缩放：嵌入式图表的交互难题

图表嵌在可滚动的页面里，滚轮事件有冲突：用户滚轮是想翻页，还是想缩放图表？

trade_canvas 的解法：

```typescript
// ChartView.tsx（简化版）
const onWheel = (e: WheelEvent) => {
  const isCtrlOrCmd = e.ctrlKey || e.metaKey;
  if (!isCtrlOrCmd) {
    e.preventDefault();  // 普通滚轮 → 留给页面滚动
    return;
  }
  // Ctrl+滚轮 → 让 Lightweight Charts 处理缩放
};

el.addEventListener("wheel", onWheel, { passive: false, capture: true });
```

规则很简单：

- 普通滚轮 → 页面滚动
- Ctrl/Cmd + 滚轮 → 图表缩放
- 双指捏合 → 图表缩放（`pinch: true`）
- 鼠标拖拽 → 图表平移（`pressedMouseMove: true`）

`capture: true` 很关键——它让事件在捕获阶段就被拦截，比 Lightweight Charts 内部的处理更早。就像门卫在大门口检查，而不是等人进了大厅再查。

---

## 8. 组件结构：一个大组件 + 多个小 Hook

ChartView 是一个约 2950 行的大组件。为什么不拆成更小的组件？

因为图表渲染有大量共享状态——chart 实例、series 引用、overlay catalog、各种 ref。如果拆成子组件，这些状态要么通过 props 层层传递，要么通过 Context 共享，都会增加复杂度。

trade_canvas 的策略是：**组件不拆，逻辑拆**。

```text
ChartView.tsx（2950 行，一个组件）
  ├── useLightweightChart.ts    → 图表初始化
  ├── useReplayPackage.ts       → 回放包管理
  ├── useFibPreview.ts          → Fib 预览
  ├── candles.ts                → K线合并逻辑
  ├── ws.ts                     → WS 消息解析
  ├── sma.ts                    → SMA 计算
  ├── barSpacing.ts             → Bar 间距管理
  ├── timeFormat.ts             → 时间格式化
  ├── timeframe.ts              → 时间框架转换
  └── draw_tools/
      ├── types.ts              → 绘图工具类型
      ├── chartCoord.ts         → 坐标转换
      ├── fib.ts                → Fib 计算
      ├── PositionTool.tsx      → 仓位工具组件
      ├── FibTool.tsx           → Fib 工具组件
      ├── MeasureTool.tsx       → 测量工具组件
      └── useFibPreview.ts      → Fib 预览 Hook
```

纯计算逻辑（合并、解析、计算）抽到独立文件，UI 交互逻辑（绘图工具）抽到子组件，但核心渲染编排留在 ChartView 里。

就像一个乐队指挥——指挥（ChartView）站在台上统筹全局，但每个乐手（Hook/工具）各自练好自己的部分。指挥不需要拆成"管弦乐指挥"和"打击乐指挥"，因为他需要同时听到所有声部。

---

## 9. 这套设计背后的工程范式

### 9.1 "Series 即图层"模式

每种数据一个 Series，互不干扰。K线更新不影响笔，笔更新不影响中枢。Lightweight Charts 内部处理渲染合成。

### 9.2 "声明式同步"模式

`rebuildOverlayPolylinesFromOverlay` 不是"增量添加"，而是"声明目标状态，框架自动 diff"。这避免了手动跟踪"哪个 Series 是新增的、哪个该删除"。

### 9.3 "Ref 管理生命周期"模式

Series 实例存在 Ref 里而不是 State 里。因为 Series 的变化不需要触发 React 重渲染——它自己会更新画面。State 只用于需要触发 UI 更新的数据（如计数器、可见性开关）。

### 9.4 "Canvas 补位"模式

Lightweight Charts 画不了的（矩形、自定义线条），用原生 Canvas 叠加。不是替换，而是补位。选择库的能力边界，用原生 API 扩展。

### 9.5 "统一接口"模式

三种绘图工具共享相同的 Props 接口。新增工具只需实现同一接口，不需要修改 ChartView 的管理逻辑。

---

## 10. 代码锚点（按渲染层次阅读）

| 文件 | 职责 |
| ------ | ------ |
| `frontend/src/widgets/chart/useLightweightChart.ts` | 图表初始化 + Series 创建 + Markers 插件 |
| `frontend/src/widgets/ChartView.tsx:767` | `syncMarkers` 三源合并 |
| `frontend/src/widgets/ChartView.tsx:801` | `rebuildPivotMarkersFromOverlay` 枢轴标记重建 |
| `frontend/src/widgets/ChartView.tsx:908` | `rebuildPenPointsFromOverlay` 笔折线重建 |
| `frontend/src/widgets/ChartView.tsx:943` | `rebuildOverlayPolylinesFromOverlay` 覆盖层多边形重建 |
| `frontend/src/widgets/chart/candles.ts` | K线合并逻辑 |
| `frontend/src/widgets/chart/sma.ts` | SMA 均线计算 |
| `frontend/src/widgets/chart/draw_tools/types.ts` | 绘图工具类型定义 |
| `frontend/src/widgets/chart/draw_tools/PositionTool.tsx` | 仓位工具 |
| `frontend/src/widgets/chart/draw_tools/FibTool.tsx` | 斐波那契工具 |
| `frontend/src/widgets/chart/draw_tools/MeasureTool.tsx` | 测量工具 |
| `frontend/src/widgets/chart/draw_tools/useFibPreview.ts` | Fib 预览（requestAnimationFrame） |
| `frontend/src/widgets/chart/draw_tools/chartCoord.ts` | 坐标转换（像素 ↔ 价格/时间） |

---

## 11. 过关自测

1. 为什么覆盖层 polyline 用 Map 管理 Series，而不是每次清空重建？
2. `syncMarkers` 为什么要把三种 marker 合并成一个数组？能不能分开提交？
3. Canvas 层和 Lightweight Charts 层各自适合画什么？为什么不全用 Canvas？
4. `requestAnimationFrame` 在 Fib 预览中解决了什么问题？如果直接在 mousemove 里更新会怎样？
5. ChartView 为什么不拆成多个子组件？什么时候应该拆，什么时候不该拆？

如果你能把这 5 题讲清楚，你就理解了"图表渲染不是调一个 `setData` 就完事"，而是一套多层协作、声明式同步、性能敏感的渲染架构。
