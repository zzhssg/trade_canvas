---
title: PRD · Replay 复盘模式 v1（包补齐 + 定点查询 + 播放差值更新）
status: done
owner:
created: 2026-02-06
updated: 2026-02-09
---

## 背景

trade_canvas 的主链路约束是「closed candle 为权威输入」，并要求 replay/live 同口径可复现（同输入同输出）。

当前仓库现状（简述）：
- 前端已有 `/replay` 路由，但尚未形成“复盘模式”的完整交互与数据链路（默认不启用；右侧 Replay 面板为占位）。
- 后端已有 `GET /api/frame/at_time`（点查世界状态：因子切片 + draw delta），并具备 fail-safe 对齐门禁。
- 后端已有 Overlay Replay Package（window + checkpoint/diff + catalog_base/patch）的服务实现雏形，但尚未对外暴露 API，也尚未接入前端。

本 PRD 的目标是：把“复盘模式”从占位升级为可用的研究/验收能力，并为后续演进（ReplayFrame、DeltaLedger）提供稳定接口与门禁。

关联文档（SoT/设计参考）：
- `docs/core/contracts/replay_frame_v1.md`
- `docs/plan/2026-02-02-replay-engine-v1.md`
- `docs/plan/2026-02-04-replay-overlay-package-v1-mvp.md`
- `docs/core/api/v1/http_world.md`

## 目标 / 非目标

### 目标（v1 可验收）
1) 前端可开启/关闭复盘模式，并且“隐藏未来 K 线”（只显示 <= 当前回放指针的 bars）。
2) 开启复盘时自动检测“最近 2000 根 closed K 线”覆盖度：不足则触发补齐下载（backfill），直到可构建复盘包。
3) 支持定点查询某一时刻 `t` 的：
   - 因子数据（按因子分类，以结构化 JSON 展示在右侧 Replay 面板）
   - 绘图数据（体现到图中，包含 history/head 语义的视觉表达）
4) 支持 K 线播放（play/pause/seek/调速），以“差值更新”为主保证流畅与一致性：
   - K 线：append/update 优先；大跳 seek 才 rebase setData
   - 绘图/因子：按 package 的 delta 增量更新（window 预取，避免每帧 HTTP 点查）

### 非目标（v1 不做）
- 不实现多品种/多 timeframe 并行复盘（v1 聚焦单 `series_id`）。
- 不引入完整的 DeltaLedger 写路径（v1 以 replay package 为工程化落地载体）。
- 不把 forming 蜡烛纳入因子/策略真源口径（forming 仅用于展示，不进入 replay 口径）。

## 术语与不变量（硬门禁）

- `series_id`：`{exchange}:{market}:{symbol}:{timeframe}`，例如 `binance:futures:BTC/USDT:1m`
- `aligned_time`：`floor_time(series_id, at_time)`，必须落在 closed candle 上
- `candle_id`：`{series_id}:{aligned_time}`

硬门禁（必须可测试）：
1) 复盘模式的所有数据都必须对齐到同一个 `candle_id`
2) fail-safe：任一组件未 ready 不得输出“看似可用但已漂移”的结果
3) 同输入同输出：固定 fixtures 输入，重复 seek/播放不漂移（overlay 不“越回越多”、因子不“越看越变”）

## 用户功能设计（PRD）

### 功能 1：开启与关闭复盘模式

入口：
- TopBar 提供 `Replay` 开关（或在 `/replay` 页面提供 “Replay Mode: ON/OFF” 明确开关）
- 默认关闭（前端：`VITE_ENABLE_REPLAY_V1=0`；后端：kill-switch 默认关闭）

状态机（前端）：
- OFF：live 模式（WS follow + live frame/delta）
- ON：replay 模式（package 驱动的 playback；不订阅 WS；隐藏未来 bars）

切换规则：
- OFF -> ON：进入“覆盖检测/补齐/构建包”流程（功能 2）
- ON -> OFF：清理 replay 缓存（window cache、cursor、overlay catalog 等），回到 live 数据流

### 功能 2：开启复盘时自动检测覆盖度，不足则补齐下载

用户期望：
- 用户点击开启复盘后，不需要自己判断“数据是否够 2000 根”
- 若缺失则自动补齐（可见进度与错误提示）

覆盖度判定（v1）：
- 目标：`window_candles=2000` 根 closed candles
- 以 `CandleStore.head_time(series_id)` 为上界 `to_time`
- 若 store 内可用闭合 K 数量 < 2000，则视为 coverage 不足

补齐策略（建议）：
- 优先复用现有市场数据源配置：
  - `TRADE_CANVAS_MARKET_HISTORY_SOURCE=freqtrade`：优先从 freqtrade datadir 补齐（可扩展为“非空也允许补齐 tail”）
  - 否则：使用 CCXT backfill（复用 ingest supervisor 的 backfill 能力）
- 补齐的同时必须确保 factor/overlay 写链路同步推进到同一 `to_time`（否则后续包构建将触发 fail-safe）

前端交互（建议）：
- 右侧 Replay 面板显示：
  - coverage 进度：`candles_ready / 2000`
  - backfill 状态：downloading / indexing / done / error
  - 错误时提供“重试”按钮与可复制的诊断信息（series_id、timeframe、最后写入时间）

### 功能 3：定点查询 t 时刻的因子数据与绘图数据

用户操作：
- 在 replay 播放控制条上拖动到某个 idx（或输入 `at_time`）
- 或在图中点击/移动十字线选择一个 bar（可选）

前端展示（右侧 Replay 面板，建议信息架构）：
- 顶部：当前 `candle_id / aligned_time / idx`
- Tabs：
  - `Factors`：展示 `factor_slices.snapshots`，按 `factor_name` 分组（结构化 JSON）
  - `Draw`：展示当前 active 的 overlay 指令摘要（active_ids 数量、pivot/pen 等计数）
  - `Raw Frame`（debug）：展示完整 frame JSON（用于排障与对拍）
- JSON 展示要求：
  - 可折叠（按 factor 分类、history/head 分区）
  - 提供搜索（按 key/值过滤）
  - 提供 Copy（复制当前 frame 或单 factor 的 JSON）

绘图表现（图中）：
- history 与 head 的视觉语义必须稳定：
  - history：实线/更高不透明度
  - head（候选/未确认）：虚线/更低不透明度
- 同一条 overlay 在不同 t 下的“确认/候选”语义不得漂移（否则会造成解释成本暴涨）

### 功能 4：K 线播放（差值更新，保证流畅与一致性）

播放控制（建议）：
- Play/Pause
- Step ±1（逐根）
- Seek（拖动范围条）
- Speed（例如 1x/2x/5x/10x）

性能策略（v1 必须遵守）：
- K 线数据写入：
  - forward：优先 `series.update(bar)`（append/update last）
  - seek 大跳：对“目标窗口”执行一次 `setData(window)` rebase
- overlay/因子：
  - 不允许每帧都用 `GET /api/frame/at_time` 点查（会导致 2000 次请求+抖动）
  - 必须以 replay package 的 window + delta 驱动更新；接近窗口边界时预取下一窗

一致性策略：
- 任何一次 seek/播放都必须能恢复到同一“t 帧”（对齐 + 幂等）
- 遇到 out-of-sync（例如 overlay 未准备到 to_time）必须 fail-safe：停止播放并提示原因

## 后端：数据结构（Contracts / Data Model）

### 设计原则
- 包必须可复现（cache_key 稳定），且可按 window 增量读取（避免首屏一次性拉 2000 帧）。
- 包必须同时承载：
  - K 线 bars（闭合 K）
  - 每个 t 的“全量因子数据 + 全量绘图数据”（可通过 checkpoint+diff 重建）
  - “差值更新数据”（用于从 idx -> idx+1 的增量 apply）

### 存储协议（SQLite）
- v1 采用 SQLite 包落盘（每个 cache_key 一个 DB），并强制 `history/head` 分离。
- 详细协议见：`docs/core/contracts/replay_package_v1.md`

### v1 建议数据结构（草案）

1) 元信息
- `ReplayPackageMetadataV1`
  - `schema_version: 1`
  - `series_id: string`
  - `timeframe_s: int`
  - `total_candles: int`（<= 2000）
  - `from_candle_time: int`、`to_candle_time: int`
  - `window_size: int`（例如 200 或 500）
  - `snapshot_interval: int`（例如 25）
  - `idx_to_time: string`（文档字段，明确 idx -> time 映射）

2) Window 形状（每窗独立可重建）
- `ReplayWindowV1`
  - `window_index, start_idx, end_idx`（end exclusive）
  - `kline: CandleClosed[]`（或 lightweight-charts 兼容的 bar）
  - `frame_checkpoints: ReplayFrameCheckpointV1[]`
  - `frame_diffs: ReplayFrameDiffV1[]`

3) 帧（t 时刻全量）
- `ReplayFrameV1`（建议与 `WorldStateV1` 对齐，字段尽量复用）
  - `schema_version: 1`
  - `series_id`
  - `time: { at_time, aligned_time, candle_id }`
  - `factor_slices: GetFactorSlicesResponseV1`
  - `draw_state: DrawDeltaV1`（要求 `to_candle_time == aligned_time`）

4) checkpoint/diff（示意）
- `ReplayFrameCheckpointV1`
  - `at_idx: int`
  - `frame: ReplayFrameV1`（全量）
- `ReplayFrameDiffV1`
  - `at_idx: int`
  - `delta: ReplayDeltaV1`
- `ReplayDeltaV1`（差值更新）
  - `kline_update: CandleClosed`（idx 对应的 bar）
  - `draw_delta: DrawDeltaV1`（cursor/patch）
  - `factor_delta: object`（v1 可先为“局部 patch”或“factor_events 增量”，细节见实现阶段）

说明：
- “每一时刻全量”可通过 checkpoint + diff 重建得到，不强制每个 idx 都直接存 `ReplayFrameV1`。
- v1 可以先做到：每窗起点与若干间隔点提供 `frame_checkpoints`，其余 idx 用 `draw_delta + factor_delta` 重放。

### 缓存与一致性（cache_key）

cache_key 推荐包含：
- `schema`（固定字符串）
- `series_id`
- `to_candle_time`
- `window_candles/window_size/snapshot_interval`
- `candle_store_head_time`（或 candles 的 fingerprint）
- `factor_store_last_event_id`（可用 `MAX(factor_events.id)` 近似）
- `overlay_store_last_version_id`（已存在）

## 后端：API（建议）

目标：前端开启复盘时可以“只读探测 → 补齐/构建 → 分窗加载 → 播放/seek”。

建议新增一组 `/api/replay/*`（全部受 kill-switch 控制，默认关闭）：

1) 覆盖/就绪探测（只读，不隐式计算）
- `GET /api/replay/read_only?series_id&to_time?&window_candles=2000&window_size=...&snapshot_interval=...`
  - 返回：`done | build_required | coverage_missing | out_of_sync`

2) 补齐（显式触发 backfill）
- `POST /api/replay/ensure_coverage`
  - 入参：`series_id, target_candles=2000, to_time?`
  - 返回：job_id + 进度（可轮询）

3) 构建（显式触发）
- `POST /api/replay/build`
  - 返回：`building | done` + job_id + cache_key

4) 状态（轮询）
- `GET /api/replay/status?job_id&include_preload=1`
  - done 时可选返回 `metadata + preload_window`（减少首屏请求）

5) 分窗读取
- `GET /api/replay/window?job_id&target_idx=...`
  - 返回：包含目标 idx 的 `ReplayWindowV1`

回滚策略：
- 后端 kill-switch：`TRADE_CANVAS_ENABLE_REPLAY_V1=0`（新 endpoints 返回 404）

## 前后端数据链路（用户点击 Replay 的一次闭环）

### 入口链路（Enable）
1) FE：用户开启 replay
2) FE -> BE：`GET /api/replay/read_only`
3) 若 `coverage_missing`：
   - FE -> BE：`POST /api/replay/ensure_coverage`，轮询直到 `candles_ready >= 2000` 且 factor/overlay ready
4) 若 `build_required`：
   - FE -> BE：`POST /api/replay/build`，轮询 `GET /api/replay/status`
5) done：
   - FE：拿到 `metadata + preload_window`，初始化 replay state（idx=0 或 idx=最后一根）

### 播放/Seek 链路（Playback）
- 每次 idx 变化：
  - K 线：append/update 或 rebase setData
  - overlay/因子：按 window 内的 `diff` apply
- 接近 window 边界：
  - FE 预取下一窗 `GET /api/replay/window`

### 点查链路（Inspect）
- 右侧 Replay 面板展示“当前 idx 对应的 frame”（由 replay state 重建）
- 可选提供 “Verify” 按钮：抽样调用 `GET /api/frame/at_time` 对拍（用于 debug，不参与主渲染链路）

## 开关与配置（必须）

前端（Vite env）：
- `VITE_ENABLE_REPLAY_V1=1`：显示复盘模式入口与控制条（默认 0）
- `VITE_ENABLE_REPLAY_PACKAGE_V1=1`：启用 replay package 驱动（默认 0；未启用时可退化到点查 demo，但不满足性能目标）

后端（kill-switch，默认关闭）：
- `TRADE_CANVAS_ENABLE_REPLAY_V1=1`：启用 `/api/replay/*`（默认 0）
- `TRADE_CANVAS_ENABLE_REPLAY_ENSURE_COVERAGE=1`：允许自动补齐下载（默认 0，逐步放开）

## 验收标准（v1）

功能验收（必须）：
1) 开关：可 ON/OFF，OFF 后回到 live，不残留 replay UI 状态
2) 覆盖检测：当 candles < 2000 时自动补齐并可见进度；补齐失败有可诊断提示
3) 定点查询：seek 任意 idx，右侧 JSON 展示稳定；重复 seek 不漂移
4) 绘图一致性：同一 window 内前进/后退 seek，overlay 不“越回越多”（active_ids 与计数稳定）
5) 播放流畅：forward 播放不触发每帧全量 setData，不触发每帧 HTTP 点查
6) fail-safe：制造 out-of-sync（overlay head < to_time）时，复盘必须停止并提示 `ledger_out_of_sync:*`

最小门禁命令（实现阶段必须固定）：
- 前端：`cd frontend && npm run build`
- 后端：`pytest -q`
- 集成/E2E：`E2E_PLAN_DOC=docs/plan/2026-02-06-replay-prd-v1.md bash scripts/e2e_acceptance.sh`

## E2E 用户故事（门禁骨架）

Persona：研究员  
Goal：在 Replay 模式回放最近 2000 根 K，反复 seek（含向后）并确认 factor+overlay 对齐且不漂移。

Scenario（必须写死关键数值，便于复现）：
- series_id：`binance:futures:BTC/USDT:1m`
- 先写入 2100 根 closed candles（保证 tail=2000）
- 打开 replay：
  - 若 coverage_missing：自动补齐直至 done
  - 若 build_required：自动 build 直至 done
- seek：`idx=10 -> 300 -> 20`（同窗内向后 seek 不漂移）
- 断言：
  - `candle_id` 对齐（frame 内各组件一致）
  - overlay 计数稳定（例如 pivot markers 数量、pen polyline 点数不随 seek 变大）
  - 网络请求窗口化（`/window` 不随 seek 次数线性增长）

## 里程碑（建议拆步）

1) M0（文档/契约）：本 PRD + 对应 contracts/api 文档（done）
2) M1（后端）：`/api/replay/*` 最小闭环 + 仅 overlay package（窗口化、seek 不漂移）
3) M2（前端）：Replay UI + window cache + 播放控制 + 右侧 JSON Inspector
4) M3（验收）：Playwright E2E 纳入 `scripts/e2e_acceptance.sh`，并产出证据（trace/screenshot/log）

## 风险与回滚

风险：
- payload 体积：frame checkpoints 过密会导致窗口 payload 过大（需 window_size/snapshot_interval 控制）
- 计算耗时：补齐下载 + factor/overlay 追赶可能慢（需进度条与可取消）
- 漂移风险：任何 “隐式全量重算” 或 “非对齐输出” 会造成复盘不可用（必须 fail-safe）

回滚：
- 后端：关闭 `TRADE_CANVAS_ENABLE_REPLAY_V1`（/api/replay 404）
- 前端：关闭 `VITE_ENABLE_REPLAY_V1`/`VITE_ENABLE_REPLAY_PACKAGE_V1`（UI 不暴露 replay）
- 代码级：每一步保持 atomic commit（便于 `git revert`）

## 变更记录
- 2026-02-06: 创建（草稿）
