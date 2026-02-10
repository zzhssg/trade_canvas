# 项目架构图

> status: draft | 2026-02-10

## 1. 系统总览

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Trade Canvas                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────────────────────┐    ┌─────────────────────────────────┐ │
│  │         Frontend (React)        │    │       Backend (FastAPI)         │ │
│  │                                 │    │                                 │ │
│  │  ┌───────────┐ ┌─────────────┐  │    │  ┌───────────┐ ┌─────────────┐  │ │
│  │  │  Pages    │ │   Widgets   │  │    │  │  REST API │ │  WebSocket  │  │ │
│  │  │  /live    │ │  ChartView  │  │◄──►│  │  /api/*   │ │  /ws/*      │  │ │
│  │  │  /replay  │ │  FactorPanel│  │    │  └───────────┘ └─────────────┘  │ │
│  │  │  /backtest│ └─────────────┘  │    │         │             │         │ │
│  │  └───────────┘        ▲         │    │         ▼             ▼         │ │
│  │        │              │         │    │  ┌─────────────────────────┐    │ │
│  │        ▼              │         │    │  │    Orchestrators        │    │ │
│  │  ┌─────────────────────────┐    │    │  │  Factor │ Overlay │Plot │    │ │
│  │  │   State (Zustand)       │    │    │  └─────────────────────────┘    │ │
│  │  │  uiStore │ factorStore  │    │    │         │             │         │ │
│  │  └─────────────────────────┘    │    │         ▼             ▼         │ │
│  │                                 │    │  ┌─────────────────────────┐    │ │
│  └─────────────────────────────────┘    │  │   SQLite Stores         │    │ │
│                                         │  │  Candle│Factor│Overlay  │    │ │
│                                         │  └─────────────────────────┘    │ │
│                                         │         ▲                       │ │
│                                         │         │                       │ │
│                                         │  ┌─────────────────────────┐    │ │
│                                         │  │   Ingest Supervisor     │    │ │
│                                         │  │     (Binance WS)        │    │ │
│                                         │  └───────────┬─────────────┘    │ │
│                                         │              │                  │ │
│                                         └──────────────┼──────────────────┘ │
│                                                        │                    │
└────────────────────────────────────────────────────────┼────────────────────┘
                                                         │
                                                         ▼
                                              ┌─────────────────────┐
                                              │   Exchange (Binance)│
                                              │   via Binance WS    │
                                              └─────────────────────┘
```

## 1.1 2026-02-10 后端硬化增量（M0-M3）

- 新增 `backend/app/container.py`：集中装配 runtime、orchestrator、store、hub，`main.py` 只保留入口与路由挂载。
- 新增 `backend/app/flags.py`：集中主链路开关（含 `TRADE_CANVAS_ENABLE_INGEST_PIPELINE_V2`、`TRADE_CANVAS_ENABLE_READ_STRICT_MODE`）。
- 新增 `backend/app/pipelines/ingest_pipeline.py`：统一 closed 写链路（store/factor/overlay/publish）。
- 新增 `backend/app/read_models/factor_read_service.py`：统一 factor 读模型；strict 模式仅读不写，落后即 `409`。
- `MarketRuntime` 显式注入 `flags + ingest_pipeline`，路由层改为从 runtime 读取开关与能力。

## 2. 目录结构

```
trade_canvas/
├── frontend/                    # React + TypeScript 前端
│   └── src/
│       ├── pages/              # 页面: Live, Replay, Backtest, Settings
│       ├── layout/             # 布局: AppShell
│       ├── parts/              # UI组件: TopBar, Sidebar, BottomTabs
│       ├── widgets/            # 图表组件: ChartView
│       ├── state/              # Zustand 状态: uiStore, factorStore
│       ├── services/           # 业务逻辑: factorCatalog
│       ├── contracts/          # API 类型定义 (OpenAPI 生成)
│       └── lib/                # 工具函数
│
├── backend/                     # Python FastAPI 后端
│   └── app/
│       ├── main.py             # FastAPI 入口 + 所有 API 端点
│       ├── schemas.py          # Pydantic 数据模型
│       ├── store.py            # CandleStore (SQLite)
│       ├── factor_*.py         # 因子模块: orchestrator, store
│       ├── overlay_*.py        # 覆盖层模块: orchestrator, store
│       ├── plot_*.py           # 绘图模块: orchestrator, store
│       ├── ingest_*.py         # 数据摄入: supervisor, binance_ws
│       ├── ws_hub.py           # WebSocket 连接管理
│       ├── pivot.py            # 枢纽计算
│       ├── pen.py              # 笔段计算
│       └── zhongshu.py         # 中枢计算
│
├── docs/                        # 文档
│   └── core/                   # 核心文档 + 契约
│
├── Strategy/                    # Freqtrade 策略
└── scripts/                     # 脚本工具
```

## 3. 技术栈

| 层级 | 技术 |
|------|------|
| **前端框架** | React 18 + TypeScript |
| **状态管理** | Zustand (持久化) |
| **图表库** | Lightweight Charts |
| **样式** | Tailwind CSS |
| **构建** | Vite |
| **后端框架** | FastAPI (Python) |
| **数据库** | SQLite |
| **交易所接口** | Binance WebSocket |
| **回测** | Freqtrade |

## 4. 数据流

### 4.1 实时模式 (Live)

```
┌──────────┐    subscribe     ┌──────────┐    start_ingest    ┌──────────┐
│ Frontend │ ───────────────► │  WsHub   │ ─────────────────► │ Ingest   │
│ ChartView│                  │ /ws/market│                   │Supervisor│
└──────────┘                  └──────────┘                    └────┬─────┘
     ▲                              │                              │
     │                              │                              ▼
     │                              │                       ┌──────────┐
     │         candle_closed        │     Binance WS     │  Binance │
     │ ◄────────────────────────────┤ ◄─────────────────────│    WS    │
     │                              │                       └──────────┘
     │                              │
     │                              ▼
     │                       ┌──────────────┐
     │                       │ Orchestrators │
     │                       │ Factor→Overlay│
     │                       └──────┬───────┘
     │                              │
     │                              ▼
     │                       ┌──────────────┐
     │    GET /api/draw/delta│   Stores     │
     └───────────────────────│ SQLite (3个) │
                             └──────────────┘
```

### 4.2 回放模式 (Replay)

```
┌──────────┐  GET /api/frame/at_time  ┌──────────┐
│ Frontend │ ───────────────────────► │ Backend  │
│ ReplayPage│                         │          │
└──────────┘                          └────┬─────┘
     ▲                                     │
     │                                     ▼
     │                              ┌──────────────┐
     │      WorldStateV1           │   Stores     │
     │ ◄───────────────────────────│ query at_time│
     │   (candles + factors +      └──────────────┘
     │    overlays at timestamp)
     │
```

### 4.3 回测模式 (Backtest)

```
┌──────────┐  POST /api/backtest/run  ┌──────────┐
│ Frontend │ ───────────────────────► │ Backend  │
│BacktestPage│                        │          │
└──────────┘                          └────┬─────┘
     ▲                                     │
     │                                     ▼
     │                              ┌──────────────┐
     │      BacktestResponse       │  Freqtrade   │
     │ ◄───────────────────────────│   Runner     │
     │   (trades, stats, logs)     └──────────────┘
     │   (trades, stats, logs)     └──────────────┘
     │
```

## 5. 核心模块

### 5.1 因子计算链路

#### 5.1.1 因子重算与状态回放护栏

- 因子链路采用 **fingerprint 自动重算**：当编排逻辑或关键配置变更时，`FactorOrchestrator` 会清理旧因子产物并从最新保留窗口重建，避免“代码已变但旧因子仍被复用”。
- 状态回放采用两段读取策略：
  - 常态：`LIMIT` 读取最近事件，快速重建增量状态。
  - 命中上限：自动切换为 `paged_full_scan`（按 `candle_time,id` 分页遍历），保证给定时间窗内事件不被截断。
- 对外通过 debug 事件 `factor.state_rebuild.limit_reached` 暴露降级信息（含 `mode=paged_full_scan`），便于排查“重建窗口过大”场景。

```
CandleClosed Event
       │
       ▼
┌──────────────────┐
│ FactorOrchestrator│
└────────┬─────────┘
         │
         ├──────────────────────────────────────┐
         ▼                                      ▼
┌─────────────────┐                    ┌─────────────────┐
│  pivot.py       │                    │  pen.py         │
│  compute_major  │ ──────────────────►│  build_pens     │
│  compute_minor  │    major_pivots    │  from_pivots    │
└─────────────────┘                    └────────┬────────┘
                                                │
                                                ▼
                                       ┌─────────────────┐
                                       │  zhongshu.py    │
                                       │  build_zhongshu │
                                       │  from_pens      │
                                       └─────────────────┘
```

### 5.2 覆盖层系统

```
┌─────────────────┐
│ FactorStore     │  factor events (pivot, pen, zhongshu)
└────────┬────────┘
         │
         ▼
┌─────────────────────┐
│ OverlayOrchestrator │  构建覆盖层指令
└────────┬────────────┘
         │
         ├─────────────────┬─────────────────┐
         ▼                 ▼                 ▼
    ┌─────────┐      ┌──────────┐     ┌──────────┐
    │ Marker  │      │ Polyline │     │ (其他)   │
    │ 点标记  │      │ 线段     │     │          │
    └─────────┘      └──────────┘     └──────────┘
         │                 │                 │
         └─────────────────┴─────────────────┘
                           │
                           ▼
                  ┌─────────────────┐
                  │  OverlayStore   │  版本化存储
                  └─────────────────┘
```

### 5.3 前端图表渲染

```
┌─────────────────────────────────────────────────────────────┐
│                      ChartView.tsx                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │ Candlestick │  │ SMA Lines   │  │ Overlays            │  │
│  │ Series      │  │ (5, 20)     │  │ (marker, polyline)  │  │
│  └─────────────┘  └─────────────┘  └─────────────────────┘  │
│                                                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │ Pen Lines   │  │ Zhongshu    │  │ Entry Signals       │  │
│  │ (笔段)      │  │ (中枢)      │  │ (标记)              │  │
│  └─────────────┘  └─────────────┘  └─────────────────────┘  │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐    │
│  │              Lightweight Charts Engine              │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## 6. API 端点概览

### REST API

| 路径 | 方法 | 说明 |
|------|------|------|
| `/api/market/candles` | GET | 获取蜡烛数据 |
| `/api/market/top_markets` | GET | 获取热门市场 |
| `/api/factor/catalog` | GET | 获取因子目录（前端因子开关动态配置） |
| `/api/factor/slices` | GET | 获取因子快照 |
| `/api/draw/delta` | GET | 获取绘图增量 |
| `/api/frame/live` | GET | 获取实时世界状态 |
| `/api/frame/at_time` | GET | 获取指定时间状态 |
| `/api/backtest/run` | POST | 运行回测 |

### WebSocket

| 路径 | 说明 |
|------|------|
| `/ws/market` | 市场数据订阅 (candle_closed, candle_forming) |
| `/ws/debug` | 调试事件流 |

## 7. 数据存储

### SQLite 表结构

```
CandleStore (store.py)
├── candles (series_id, candle_time, open, high, low, close, volume)
└── idx_candles_series_time

FactorStore (factor_store.py)
├── factor_events (series_id, factor_name, kind, candle_time, visible_time, payload)
└── factor_series_state (series_id, head_time)

OverlayStore (overlay_store.py)
├── overlay_instruction_versions (version_id, instruction_id, kind, payload)
└── overlay_series_state (series_id, head_time)

PlotStore (plot_store.py)
├── plot_line_points (series_id, feature_key, candle_time, value)
└── plot_overlay_events (series_id, kind, payload)
```

## 8. 关键文件索引

| 文件 | 职责 |
|------|------|
| [main.py](../../backend/app/main.py) | FastAPI 入口 + API 端点 |
| [schemas.py](../../backend/app/schemas.py) | Pydantic 数据模型 |
| [ChartView.tsx](../../frontend/src/widgets/ChartView.tsx) | 图表渲染引擎 |
| [uiStore.ts](../../frontend/src/state/uiStore.ts) | UI 状态管理 |
| [factor_orchestrator.py](../../backend/app/factor_orchestrator.py) | 因子计算编排 |
| [overlay_orchestrator.py](../../backend/app/overlay_orchestrator.py) | 覆盖层构建 |
| [ingest_supervisor.py](../../backend/app/ingest_supervisor.py) | 数据摄入管理 |
| [ws_hub.py](../../backend/app/ws_hub.py) | WebSocket 管理 |
