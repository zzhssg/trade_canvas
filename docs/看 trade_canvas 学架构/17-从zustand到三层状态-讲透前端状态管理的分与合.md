---
title: 第17关：从 Zustand 到三层状态，讲透前端状态管理的分与合
status: done
created: 2026-02-11
updated: 2026-02-11
---

# 第17关：从 Zustand 到三层状态，讲透前端状态管理的分与合

从这一关开始，我们进入前端。

后端的数据已经算好了、对齐了、打包了。但用户看到的不是 JSON，而是图表、按钮、面板。**数据怎么变成画面？** 这是前端要回答的核心问题。

而前端的第一个难题，不是"怎么画"，而是"数据放哪"。

---

## 1. 先讲问题：为什么"数据放哪"这么难

想象你搬进一间新公寓。你有三类东西：

- **个人偏好**：窗帘颜色、空调温度、灯光亮度。这些是你的习惯，换了房间也想保留。
- **正在做的事**：桌上摊开的书、正在写的论文、打开的浏览器标签。这些是你当前的工作状态，关机就没了。
- **从外面拿回来的东西**：快递包裹、外卖、从图书馆借的书。这些不是你的，是外部世界的副本。

如果你把这三类东西全堆在一张桌子上，会怎样？

- 找东西找不到（状态混乱）
- 搬家时不知道哪些要带走（持久化混乱）
- 外卖凉了还以为是新的（缓存过期）

前端状态管理的本质，就是把这三类东西分开放。

---

## 2. trade_canvas 的三层状态架构

```text
┌─────────────────────────────────────────────┐
│  第一层：UI 偏好层（个人习惯）               │
│  useUiStore / useFactorStore                │
│  持久化到 localStorage，刷新不丢            │
├─────────────────────────────────────────────┤
│  第二层：业务领域层（正在做的事）            │
│  useReplayStore                             │
│  纯内存，刷新即清                           │
├─────────────────────────────────────────────┤
│  第三层：服务端缓存层（外面拿回来的东西）    │
│  useReplayStore.windows / useDevStore       │
│  纯内存，随时可重新获取                     │
└─────────────────────────────────────────────┘
```

每一层的规则不同，混在一起就会出问题。下面逐层拆解。

---

## 3. 第一层：UI 偏好——"你喜欢什么"

### 3.1 useUiStore：布局和导航偏好

```typescript
// frontend/src/state/uiStore.ts
interface UiState {
  exchange: "binance";           // 交易所
  market: MarketMode;            // "spot" | "futures"
  symbol: string;                // "BTC/USDT"
  timeframe: string;             // "1m" | "1h" | ...
  toolRailWidth: number;         // 工具栏宽度 44~96px
  sidebarCollapsed: boolean;     // 侧边栏折叠
  sidebarWidth: number;          // 侧边栏宽度 220~520px
  bottomCollapsed: boolean;      // 底部面板折叠
  activeSidebarTab: SidebarTab;  // 当前侧边栏标签
  activeBottomTab: BottomTab;    // 当前底部标签
  activeChartTool: ChartToolKey; // 当前图表工具（不持久化）
}
```

注意两个设计细节：

**宽度有 clamp（钳位）**：

```typescript
setToolRailWidth: (w) => set({ toolRailWidth: Math.max(44, Math.min(96, w)) }),
setSidebarWidth: (w) => set({ sidebarWidth: Math.max(220, Math.min(520, w)) }),
```

就像空调温度有上下限——你可以调，但不能调到 -50°C 或 200°C。防止用户拖拽时把布局拖崩。

**activeChartTool 不持久化**：

```typescript
persist(
  (set) => ({ ... }),
  {
    name: "tc-ui",
    version: 6,
    partialize: (state) => ({
      exchange: state.exchange,
      market: state.market,
      symbol: state.symbol,
      timeframe: state.timeframe,
      // ... 其他持久化字段
      // 注意：activeChartTool 不在这里
    }),
  }
)
```

为什么？因为"当前选中的图表工具"是临时操作状态。你关掉浏览器再打开，不应该还停留在"画斐波那契"模式——应该回到默认的"光标"模式。

就像你离开办公桌时，电脑可以记住你的桌面壁纸（持久化），但不应该记住你鼠标停在哪个位置（临时状态）。

### 3.2 useFactorStore：因子可见性偏好

```typescript
// frontend/src/state/factorStore.ts
interface FactorState {
  visibleFeatures: Record<string, boolean>;  // 因子特征可见性映射
}
```

这个 store 只管一件事：图表上哪些因子特征是可见的。

```typescript
// 用户在因子面板里勾选/取消勾选
toggleFeatureVisibility: (key) =>
  set((s) => ({
    visibleFeatures: { ...s.visibleFeatures, [key]: !s.visibleFeatures[key] },
  })),
```

它也持久化——因为"我想看 pivot 但不想看 anchor"是个人偏好，刷新后应该保留。

### 3.3 版本迁移：偏好也会"过期"

两个持久化 store 都有 `migrate` 函数：

```typescript
// uiStore: version 6
migrate(persisted, version) {
  if (version < 3) { /* 旧版本字段名变更 */ }
  if (version < 5) { /* 新增 bottomCollapsed */ }
  if (version < 6) { /* 新增 toolRailWidth */ }
  return persisted;
}
```

为什么需要迁移？

因为 localStorage 里存的是旧版本的数据。如果你直接读，可能缺字段、类型不对。`migrate` 函数就像搬家时的"整理箱"——把旧东西按新规则重新摆放。

factorStore 的迁移更复杂，因为因子特征名称会变（比如 v3 版本把 `sma_20` 改成了 `sma.20`）。

---

## 4. 第二层：业务领域——"你正在做什么"

### 4.1 useReplayStore：回放引擎的核心状态

这是最复杂的 store，因为回放是 trade_canvas 最复杂的业务流程。

```typescript
// frontend/src/state/replayStore.ts（核心字段）
interface ReplayState {
  // 模式控制
  mode: "live" | "replay";
  playing: boolean;
  speedMs: number;
  index: number;
  total: number;

  // 准备阶段
  prepareStatus: "idle" | "loading" | "ready" | "error";
  preparedAlignedTime: number | null;

  // 构建阶段
  status: "idle" | "checking" | "coverage" | "building" | "ready" | "error";
  jobId: string | null;
  cacheKey: string | null;

  // 当前帧
  frame: WorldStateV1 | null;
  currentSlices: GetFactorSlicesResponseV1 | null;
  currentCandleId: string | null;
  currentDrawActiveIds: string[];
  currentDrawInstructions: OverlayInstructionPatchItemV1[];
}
```

注意这个 store 的状态字段分成了三组：

- **模式控制**：用户在做什么（播放/暂停/快进）
- **准备阶段**：后端任务进展到哪了
- **当前帧**：此刻屏幕上应该显示什么

这三组对应回放的三个阶段：**操作 → 准备 → 渲染**。

### 4.2 为什么不持久化？

回放状态是"正在做的事"。你关掉浏览器，回放就结束了。下次打开，应该从 live 模式重新开始，而不是停在上次回放到一半的状态。

就像你在看电影，关了电视。下次打开电视，应该回到频道列表，而不是停在上次暂停的画面。

### 4.3 resetData 和 resetPackage：两种"清理"

```typescript
resetData: () => set({
  frame: null, frameLoading: false, frameError: null,
  currentSlices: null, currentCandleId: null, ...
}),

resetPackage: () => set({
  status: "idle", error: null, jobId: null, cacheKey: null,
  coverage: null, metadata: null, windows: {}, ...
}),
```

`resetData` 清理"当前帧"（换了时间点，旧帧数据作废）。
`resetPackage` 清理"构建状态"（换了参数，旧包作废）。

两者分开，是因为"换帧"和"换包"是不同的操作。拖动进度条只需要 resetData，切换交易对需要 resetPackage。

---

## 5. 第三层：服务端缓存——"从外面拿回来的东西"

### 5.1 useReplayStore.windows：回放窗口缓存

```typescript
windows: Record<number, ReplayWindowBundle>;  // 按窗口索引缓存
```

这不是"你的数据"，而是"从后端拿回来的副本"。它的特点：

- **可丢弃**：刷新页面就没了，因为随时可以重新从后端获取。
- **按需加载**：不是一次全拿，而是用户拖到哪个窗口才加载哪个。
- **有过期风险**：如果后端数据变了（新K线入库），这些缓存就过期了。

就像你从图书馆借的书——不是你的，用完要还，下次需要再借。

### 5.2 useDevStore：开发工具的工作树数据

```typescript
// frontend/src/state/devStore.ts
interface DevState {
  worktrees: WorktreeInfo[];       // 工作树列表
  loading: boolean;                // 加载中
  error: string | null;            // 错误
  selectedWorktreeId: string | null; // 选中的工作树
}
```

这个 store 存的是"从后端 API 拿回来的工作树列表"。纯服务端缓存，不持久化。

### 5.3 useDebugLogStore：调试日志缓冲

```typescript
// frontend/src/state/debugLogStore.ts
interface DebugLogState {
  events: DebugEvent[];    // 调试事件列表
  filter: DebugFilter;     // 过滤器
  query: string;           // 搜索查询
  autoScroll: boolean;     // 自动滚动
  maxEntries: number;      // 最大条目数（100~10000）
}
```

日志缓冲有一个精巧的设计——`maxEntries` 限制：

```typescript
append: (e) => set((s) => {
  const next = [...s.events, e];
  return { events: next.length > s.maxEntries ? next.slice(-s.maxEntries) : next };
}),
```

当日志超过上限时，自动丢弃最旧的。就像监控摄像头的存储——只保留最近 N 小时的录像，更早的自动覆盖。

---

## 6. 为什么选 Zustand 而不是 Redux 或 Context

### 6.1 Zustand vs Redux

Redux 需要 action → reducer → dispatch 三件套。写一个"切换侧边栏"要定义 action type、action creator、reducer case。

Zustand 一行搞定：

```typescript
toggleSidebarCollapsed: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
```

对于 trade_canvas 这种"状态多但逻辑简单"的场景，Zustand 的简洁性是碾压级的。

### 6.2 Zustand vs React Context

React Context 有一个致命问题：**任何 state 变化都会导致所有消费者重渲染。**

如果你把 uiStore 的所有状态放在一个 Context 里，用户拖动侧边栏宽度时，图表组件也会重渲染——即使图表根本不关心侧边栏宽度。

Zustand 的选择器（selector）解决了这个问题：

```typescript
// ChartView.tsx 只订阅它关心的字段
const symbol = useUiStore((s) => s.symbol);
const timeframe = useUiStore((s) => s.timeframe);
// symbol 和 timeframe 没变，ChartView 不重渲染
```

就像订报纸：Context 是"报社一有新闻就给你打电话"，Zustand 选择器是"只有体育版有新闻才通知我"。

### 6.3 Context 的正确用途

trade_canvas 里 Context 只用在一个地方：

```typescript
// frontend/src/layout/centerScrollLock.tsx
const CenterScrollLockContext = createContext<{ lock(): void; unlock(): void }>(...);
```

控制中心区域的滚动锁定。这是一个"低级别的 UI 控制"，只在布局组件内部使用，不需要全局共享。

规则很简单：**全局状态用 Zustand，局部控制用 Context。**

---

## 7. 选择器模式：精确订阅，避免无效重渲染

这是 Zustand 最重要的使用模式。trade_canvas 里有三种写法：

### 7.1 单字段选择器（最常见）

```typescript
// ChartView.tsx
const replayMode = useReplayStore((s) => s.mode);
const replayPlaying = useReplayStore((s) => s.playing);
```

每个字段单独订阅。`mode` 变了不会触发 `playing` 的重渲染。

### 7.2 整体解构（简单 store）

```typescript
// FactorPanel.tsx
const { visibleFeatures, toggleFeatureVisibility } = useFactorStore();
```

factorStore 只有一个状态字段，解构不会造成多余重渲染。

### 7.3 混合模式（跨 store）

```typescript
// ReplayPanel.tsx
const { exchange, market, symbol, timeframe } = useUiStore();
const mode = useReplayStore((s) => s.mode);
const status = useReplayStore((s) => s.status);
```

从不同 store 各取所需。uiStore 用解构（因为这几个字段经常一起用），replayStore 用选择器（因为它字段太多，解构会订阅太多）。

---

## 8. 数据流向：从用户操作到画面更新

```text
用户点击"切换到 replay 模式"
  │
  ├→ useUiStore 不变（布局不变）
  │
  ├→ useReplayStore.setMode("replay")
  │   │
  │   ├→ ReplayPanel 重渲染（显示回放控制）
  │   ├→ ChartView 重渲染（切换数据源）
  │   └→ useReplayPackage 触发（开始加载回放包）
  │       │
  │       ├→ setStatus("checking") → UI 显示"检查中"
  │       ├→ setStatus("building") → UI 显示"构建中"
  │       ├→ setStatus("ready") → UI 显示"就绪"
  │       └→ setWindowBundle(0, data) → 图表渲染第一个窗口
  │
  └→ useFactorStore 不变（可见性偏好不变）
```

注意数据流是单向的：**用户操作 → store 更新 → 组件重渲染**。没有组件直接修改另一个组件的状态。

这就是 Zustand 的"单向数据流"——和 Redux 一样的理念，但实现更轻量。

---

## 9. 这套设计背后的四条工程原则

```text
原则1：按生命周期分层
  → 持久化偏好 / 会话级业务 / 可丢弃缓存，三层不混
  → 就像公寓里的个人物品 / 工作文件 / 借来的书

原则2：选择器精确订阅
  → 组件只订阅它关心的字段，不多不少
  → 就像只订阅体育版，不是整份报纸

原则3：全局用 Zustand，局部用 Context
  → 全局状态需要跨组件共享 → Zustand
  → 局部控制只在父子间传递 → Context
  → 不混用，不纠结

原则4：重置粒度匹配操作粒度
  → 换帧 → resetData（只清当前帧）
  → 换参数 → resetPackage（清整个包）
  → 不是一刀切的"全部重置"
```

---

## 10. 代码锚点（按阅读顺序）

| 概念 | 文件 | 干什么的 |
| ---- | ---- | ---- |
| UI 偏好 store | `frontend/src/state/uiStore.ts` | 布局/导航/工具偏好 + 持久化 |
| 因子可见性 store | `frontend/src/state/factorStore.ts` | 因子特征显隐 + 持久化 + 版本迁移 |
| 回放业务 store | `frontend/src/state/replayStore.ts` | 回放引擎核心状态（纯内存） |
| 开发工具 store | `frontend/src/state/devStore.ts` | 工作树列表（服务端缓存） |
| 调试日志 store | `frontend/src/state/debugLogStore.ts` | 日志缓冲 + maxEntries 限制 |
| 滚动锁 Context | `frontend/src/layout/centerScrollLock.tsx` | 局部 UI 控制 |
| 主要消费者 | `frontend/src/widgets/ChartView.tsx` | 跨 store 选择器用法示范 |

---

## 11. 过关自测

1. 为什么 `activeChartTool` 不持久化，而 `activeSidebarTab` 要持久化？判断标准是什么？
2. useReplayStore 为什么不持久化？如果持久化了会出什么问题？
3. Zustand 选择器和 React Context 在"避免无效重渲染"上有什么本质区别？
4. `resetData` 和 `resetPackage` 为什么要分开？如果合成一个 `reset` 会怎样？
5. 三层状态（UI偏好/业务领域/服务端缓存）的分层依据是什么？用"搬家"的比喻解释。

能把这5题讲清楚，你就理解了前端状态管理不是"选哪个库"的问题，而是"数据按什么维度分类"的问题。
