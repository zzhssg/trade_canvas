---
title: 第20关：从 VITE_ENABLE 到路由守卫，讲透前端功能开关
status: done
created: 2026-02-11
updated: 2026-02-11
---

# 第20关：从 VITE_ENABLE 到路由守卫，讲透前端功能开关

上一关你学了"数据怎么画"。这一关解决"功能怎么开"。

trade_canvas 不是一个"全功能一把梭"的系统。它有大量功能处于不同的成熟度——有的已经稳定上线，有的还在灰度测试，有的只在开发环境可用。

这就像一栋大楼的电梯系统。有些楼层对所有人开放，有些楼层需要刷卡，有些楼层还在装修、根本不停靠。你不能把所有楼层都打开，也不能把所有楼层都关掉。

问题是：

- 怎么让同一套代码在不同环境表现不同？
- 怎么让前端和后端的开关协调一致？
- 怎么让用户能自己控制"看到什么"？

---

## 1. 三层开关体系

trade_canvas 的功能开关分三层：

```text
第一层：编译时开关（VITE_ENABLE_*）
  ↓ 构建时决定，写死在 JS 包里，不可运行时改
第二层：后端运行时开关（TRADE_CANVAS_ENABLE_*）
  ↓ 启动时从环境变量读取，重启才能改
第三层：用户运行时开关（visibleFeatures）
  ↓ 用户随时在 UI 上切换，立即生效
```

三层就像三道门：

- 第一道门（编译时）：大楼设计图上画没画这个房间。没画的话，砖都没砌，进不去。
- 第二道门（后端运行时）：房间建好了，但物业决定开不开门。
- 第三道门（用户运行时）：门开了，但你自己选择进不进去。

---

## 2. 第一层：编译时开关（VITE_ENABLE_*）

### 2.1 定义方式

在 `.env.development` 里设置：

```bash
# frontend/.env.development
VITE_ENABLE_DEBUG_TOOL=1
VITE_ENABLE_KLINE_HEALTH_LAMP_V2=1
```

### 2.2 消费方式

在代码里读取并转为布尔值：

```typescript
// ChartView.tsx
const ENABLE_REPLAY_V1 = String(import.meta.env.VITE_ENABLE_REPLAY_V1 ?? "1") === "1";
const ENABLE_PEN_SEGMENT_COLOR = import.meta.env.VITE_ENABLE_PEN_SEGMENT_COLOR === "1";
const ENABLE_WORLD_FRAME = String(import.meta.env.VITE_ENABLE_WORLD_FRAME ?? "1") === "1";
const ENABLE_DRAW_TOOLS = String(import.meta.env.VITE_ENABLE_DRAW_TOOLS ?? "1") === "1";
```

注意两种写法的区别：

| 写法 | 含义 | 默认值 |
| ------ | ------ | ------ |
| `String(env ?? "1") === "1"` | 没设置时默认开启 | ON |
| `env === "1"` | 没设置时默认关闭 | OFF |

`?? "1"` 就是"没说就是开"，不加就是"没说就是关"。

就像酒店的 minibar——有些酒店默认开放（你不说就能用），有些默认锁着（你不申请就用不了）。

### 2.3 开发环境特殊处理

调试工具有更精细的默认值逻辑：

```typescript
// frontend/src/debug/debug.ts
export const ENABLE_DEBUG_TOOL =
  String(import.meta.env.VITE_ENABLE_DEBUG_TOOL ?? (import.meta.env.DEV ? "1" : "0")) === "1";
```

翻译成人话：如果没设置 `VITE_ENABLE_DEBUG_TOOL`，开发环境默认开，生产环境默认关。

### 2.4 完整开关清单

```text
VITE_ENABLE_DEBUG_TOOL ────────── 调试工具面板（开发ON/生产OFF）
VITE_ENABLE_REPLAY_V1 ─────────── 回放功能（默认ON）
VITE_ENABLE_REPLAY_PACKAGE_V1 ── 回放包模式（默认OFF）
VITE_ENABLE_PEN_SEGMENT_COLOR ── 笔段着色（默认OFF）
VITE_ENABLE_ANCHOR_TOP_LAYER ─── 锚点顶层渲染（默认ON）
VITE_ENABLE_WORLD_FRAME ────────── 世界帧模式（默认ON）
VITE_ENABLE_DRAW_TOOLS ─────────── 绘图工具（默认ON）
VITE_ENABLE_TRADE_ORACLE_PAGE ── 交易预言机页面（默认ON）
VITE_ENABLE_KLINE_HEALTH_LAMP_V2  K线健康灯V2（默认OFF）
```

---

## 3. 路由守卫：编译时开关的最强用法

编译时开关最典型的用法是路由守卫——整个页面级别的开关：

```typescript
// frontend/src/App.tsx
const ENABLE_TRADE_ORACLE_PAGE = String(import.meta.env.VITE_ENABLE_TRADE_ORACLE_PAGE ?? "1") === "1";

export default function App() {
  return (
    <Routes>
      <Route path="/live" element={<LivePage />} />
      <Route path="/oracle"
        element={ENABLE_TRADE_ORACLE_PAGE ? <OraclePage /> : <Navigate to="/live" replace />}
      />
      <Route path="/replay" element={<ReplayPage />} />
    </Routes>
  );
}
```

当 `ENABLE_TRADE_ORACLE_PAGE` 为 false 时，访问 `/oracle` 会被重定向到 `/live`。用户甚至不知道这个页面存在。

这就是"路由守卫"——不是在页面里显示"功能未开放"，而是直接把路不通。就像地铁站的闸机：没开放的出口，闸机直接不转，你连站台都看不到。

---

## 4. 第二层：后端运行时开关（TRADE_CANVAS_ENABLE_*）

后端的开关体系分两级：`FeatureFlags`（基础）和 `RuntimeFlags`（完整）。

### 4.1 FeatureFlags：基础开关

```python
# backend/app/flags.py
@dataclass(frozen=True)
class FeatureFlags:
    enable_debug_api: bool
    enable_read_strict_mode: bool
    enable_whitelist_ingest: bool
    enable_ondemand_ingest: bool
    enable_market_auto_tail_backfill: bool
    market_auto_tail_backfill_max_candles: int | None
    ondemand_idle_ttl_s: int
```

加载方式：

```python
def load_feature_flags() -> FeatureFlags:
    return FeatureFlags(
        enable_debug_api=env_bool("TRADE_CANVAS_ENABLE_DEBUG_API"),
        enable_read_strict_mode=env_bool("TRADE_CANVAS_ENABLE_READ_STRICT_MODE", default=True),
        enable_whitelist_ingest=env_bool("TRADE_CANVAS_ENABLE_WHITELIST_INGEST"),
        # ...
    )
```

### 4.2 RuntimeFlags：完整开关

`RuntimeFlags` 继承 `FeatureFlags` 的值，再加上更多细粒度控制：

```python
# backend/app/runtime_flags.py
@dataclass(frozen=True)
class RuntimeFlags:
    # 从 FeatureFlags 继承
    enable_debug_api: bool
    # 因子相关
    enable_factor_ingest: bool
    enable_factor_fingerprint_rebuild: bool
    factor_pivot_window_major: int      # 不只是 bool，还有参数
    factor_pivot_window_minor: int
    factor_lookback_candles: int
    # 覆盖层相关
    enable_overlay_ingest: bool
    overlay_window_candles: int
    # 回放相关
    enable_replay_v1: bool
    enable_replay_package: bool
    # 市场数据相关
    enable_market_gap_backfill: bool
    enable_derived_timeframes: bool
    # ... 共 30+ 个开关
```

注意：后端开关不只是 `bool`，还有 `int`（窗口大小、超时时间）和 `str`（数据源选择）。这比前端的纯 bool 开关更丰富。

### 4.3 工具函数：统一的解析层

```python
# backend/app/flags.py
def env_bool(name: str, *, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return bool(default)
    return truthy_flag(raw)  # "1", "true", "yes", "on" 都算 True

def env_int(name: str, *, default: int, minimum: int = 0) -> int:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return max(int(minimum), int(default))
    try:
        return max(int(minimum), int(raw))
    except ValueError:
        return max(int(minimum), int(default))
```

`env_int` 里的 `max(minimum, ...)` 很关键——它防止用户设置不合理的值。比如 `factor_lookback_candles` 最小 100，你设成 1 也会被拉到 100。

就像空调的温度限制——你可以调，但不能低于 16 度。

### 4.4 前后端开关的对应关系

有些功能前后端都有开关，必须协调：

```text
前端                              后端
VITE_ENABLE_REPLAY_V1        ↔   TRADE_CANVAS_ENABLE_REPLAY_V1
VITE_ENABLE_REPLAY_PACKAGE_V1 ↔  TRADE_CANVAS_ENABLE_REPLAY_PACKAGE
VITE_ENABLE_KLINE_HEALTH_V2  ↔   TRADE_CANVAS_ENABLE_KLINE_HEALTH_V2
```

如果前端开了但后端没开，前端会调到不存在的 API，报 404。如果后端开了但前端没开，后端白算了，前端不展示。

所以这是"双闸门"——两边都开，水才能流过去。就像高速公路的收费站：入口和出口都要开，车才能通行。

---

## 5. 第三层：用户运行时开关（visibleFeatures）

前两层开关是开发者控制的。第三层是用户控制的——"我想看哪些因子"。

### 5.1 存储位置

```typescript
// frontend/src/state/factorStore.ts
export const useFactorStore = create(
  persist(
    (set) => ({
      visibleFeatures: {},  // { "pivot.major": true, "pen.confirmed": false, ... }
      setFeatureVisibility: (key, visible) =>
        set((s) => ({ visibleFeatures: { ...s.visibleFeatures, [key]: visible } })),
      toggleFeatureVisibility: (key) =>
        set((s) => ({ visibleFeatures: { ...s.visibleFeatures, [key]: !(s.visibleFeatures[key] ?? true) } })),
    }),
    { name: "factor-store", version: 4 }
  )
);
```

`visibleFeatures` 是一个 `Record<string, boolean>`，key 是因子特征名（如 `"pivot.major"`、`"pen.confirmed"`），value 是是否可见。

### 5.2 消费方式：effectiveVisible

```typescript
// ChartView.tsx
const effectiveVisible = useCallback((key: string): boolean => {
  const features = visibleFeaturesRef.current;
  const direct = features[key];
  const visible = direct === undefined ? true : direct;  // 没设置默认可见
  const parentKey = parentBySubKey[key];
  if (!parentKey) return visible;
  const parentVisible = features[parentKey];
  return (parentVisible === undefined ? true : parentVisible) && visible;
}, [parentBySubKey]);
```

两个关键设计：

1. **默认可见**：`direct === undefined ? true : direct`——没设置过的特征默认显示。
2. **父子联动**：如果 `pivot` 关了，`pivot.major` 和 `pivot.minor` 也跟着关。

就像文件夹权限——父文件夹设为不可见，里面的文件也看不到，即使文件本身没有被单独隐藏。

---

## 6. 三层开关的协作流程

一个功能从"代码存在"到"用户看到"，要过三道门：

```text
以"笔段着色"为例：

第一层：VITE_ENABLE_PEN_SEGMENT_COLOR === "1" ?
  ├── 否 → 代码里 ENABLE_PEN_SEGMENT_COLOR = false，整个分支被跳过
  └── 是 ↓

第二层：后端因子引擎是否产出 pen 数据？
  ├── TRADE_CANVAS_ENABLE_FACTOR_INGEST = false → 没有 pen 数据
  └── 是 ↓

第三层：用户是否勾选了"显示笔"？
  ├── visibleFeatures["pen.confirmed"] = false → 不渲染
  └── 是 → 渲染到图表上
```

三层各管各的：

- 第一层决定"代码有没有"（编译时裁剪）。
- 第二层决定"数据有没有"（后端计算）。
- 第三层决定"画不画"（前端渲染）。

---

## 7. 编译时开关的特殊优势：死代码消除

`VITE_ENABLE_*` 不只是一个 if 判断。Vite 在构建时会把 `import.meta.env.VITE_ENABLE_*` 替换为字面量字符串。如果结果是 `false`，后续的代码会被 tree-shaking 掉。

```typescript
// 源码
const ENABLE_PEN_SEGMENT_COLOR = import.meta.env.VITE_ENABLE_PEN_SEGMENT_COLOR === "1";
if (ENABLE_PEN_SEGMENT_COLOR) {
  // 100 行笔段着色逻辑
}

// 构建后（如果 VITE_ENABLE_PEN_SEGMENT_COLOR 未设置）
const ENABLE_PEN_SEGMENT_COLOR = false;
if (false) {
  // 这 100 行会被 tree-shaking 删掉
}
```

这意味着关掉的功能不只是"不执行"，而是"不存在于最终 JS 包里"。包体积更小，加载更快。

就像出版社删掉的章节——不是用白纸盖住，而是直接不印。书更薄，读者翻得更快。

---

## 8. 这套设计背后的工程范式

### 8.1 "渐进放量"模式

新功能先默认 OFF（`env === "1"`），在开发环境验证后改为默认 ON（`env ?? "1"`），最终去掉开关。这是从"实验"到"稳定"的生命周期。

### 8.2 "双闸门"模式

前后端各有独立开关，两边都开才生效。这避免了"前端上了但后端没准备好"的尴尬。

### 8.3 "frozen dataclass"模式

后端的 `FeatureFlags` 和 `RuntimeFlags` 都是 `frozen=True`——创建后不可修改。这保证了整个请求生命周期内开关状态一致，不会出现"处理到一半开关变了"。

### 8.4 "默认安全"模式

`env_int` 的 `minimum` 参数、`env_bool` 的 `default` 参数，都是防御性设计。即使环境变量设错了，系统也不会崩溃，而是回退到安全值。

### 8.5 "父子联动"模式

`effectiveVisible` 的父子检查让用户可以一键关掉整个因子类别，而不需要逐个关闭子特征。这是 UI 友好性和数据模型简洁性的平衡。

---

## 9. 代码锚点（按层次阅读）

| 文件 | 职责 |
| ------ | ------ |
| `frontend/.env.development` | 前端开发环境开关定义 |
| `frontend/src/widgets/ChartView.tsx:59-65` | 前端编译时开关声明 |
| `frontend/src/debug/debug.ts:18` | 调试工具开关（开发/生产区分） |
| `frontend/src/App.tsx:11-19` | 路由守卫（页面级开关） |
| `frontend/src/state/factorStore.ts:7-19` | 用户运行时开关（visibleFeatures） |
| `frontend/src/widgets/ChartView.tsx:716-727` | `effectiveVisible` 父子联动 |
| `backend/app/flags.py` | 后端基础开关 + 工具函数 |
| `backend/app/runtime_flags.py` | 后端完整运行时开关（30+项） |

---

## 10. 过关自测

1. `String(env ?? "1") === "1"` 和 `env === "1"` 的默认行为有什么区别？什么时候用哪种？
2. 为什么路由守卫用 `<Navigate to="/live" replace />` 而不是显示"功能未开放"页面？
3. 后端的 `FeatureFlags` 和 `RuntimeFlags` 为什么要分两级？能不能合成一个？
4. `effectiveVisible` 的"父子联动"解决了什么用户体验问题？
5. 前后端"双闸门"模式下，如果只开了一边会发生什么？怎么排查？

如果你能把这 5 题讲清楚，你就理解了"功能开关不是一个 if-else"，而是一套跨编译时、运行时、用户态的三层控制体系。
