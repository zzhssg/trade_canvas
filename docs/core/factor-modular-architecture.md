# Factor 模块化架构（2026-02）

> status: draft | updated: 2026-02-10

本文是当前 factor 主链路的实现真源，目标是回答三件事：
- 现在的 factor 是否模块化；
- 新增一个 factor 需要改哪些固定接入面；
- 如何保证回放链路与实盘链路同输入同输出。

## 1. 当前架构分层（后端）

### 1.1 写路径（closed candle -> history/head）

1) `backend/app/factor_orchestrator.py`
- 只负责调度：读 candle、维护增量窗口、按时间推进、统一写入 `FactorStore`。
- 不再内联具体因子算法，算法下沉到 processor。
- 每根 `visible_time` 按 `FactorGraph.topo_order` 调用插件 `run_tick(...)`，缺失执行钩子时 fail-fast（`factor_missing_run_tick`）。
- 状态恢复与 head 落盘同样走插件钩子（`collect_rebuild_event / bootstrap_from_history / build_head_snapshot`），不再手写 `pivot/pen/anchor` 分支。
- 与 orchestrator 配套的两块运行时职责已拆分：
  - `backend/app/factor_runtime_config.py`：统一解析 `TRADE_CANVAS_ENABLE_FACTOR_INGEST`、窗口参数、rebuild keep-candles 等运行时参数；
  - `backend/app/factor_rebuild_loader.py`：统一承载历史事件回放分桶、分页回放与 bootstrap 状态恢复，降低 orchestrator 体积与耦合。
  - `backend/app/factor_fingerprint.py`：统一承载逻辑指纹构建（文件 hash + graph/settings + 逻辑版本覆盖），避免 orchestrator 再次膨胀。
  - `backend/app/factor_fingerprint_rebuild.py`：统一承载“指纹不匹配 -> trim candles -> clear factor -> 写入新 fingerprint”的重建闸门逻辑。
  - `backend/app/factor_ingest_window.py`：统一承载 ingest 窗口规划与 candle 批读取（start_time/read_limit/process_times），避免编排器内联窗口公式。

2) `backend/app/factor_plugin_contract.py`
- `FactorPluginSpec` 统一描述插件身份与依赖声明（`factor_name` / `depends_on`）。

3) `backend/app/factor_plugin_registry.py`
- `FactorPluginRegistry` 统一做插件注册、去重、缺失报错、spec 导出。

4) `backend/app/factor_registry.py`
- `ProcessorSpec` 声明 `factor_name + depends_on`。
- 当前作为兼容层，复用 plugin registry 能力并保留旧命名。

5) `backend/app/factor_processors.py`
- `PivotProcessor` / `PenProcessor` / `ZhongshuProcessor` / `AnchorProcessor`。
- 每个 processor 只做该因子的领域计算与事件构造。
- `build_default_factor_processors()` 作为兼容入口，默认运行时装配以 `factor_default_components` 单一注册表为准。

6) `backend/app/factor_default_components.py`
- 维护默认因子的单一配对装配（`processor_builder + slice_plugin_builder`）。
- 启动时 fail-fast 校验 processor 与 slice plugin 的 `spec.factor_name` 一致。
- 新增默认因子时，默认只需在此追加一条 bundle 配置，避免双入口重复注册。

7) `backend/app/factor_manifest.py`
- `build_default_factor_manifest()` 作为默认装配真源，同时产出 `processors + slice_plugins`。
- 启动时强校验读写两侧 `factor_name/depends_on` 一致，避免“写路径新增、读路径漏接”。

8) `backend/app/factor_graph.py`
- 基于 registry 的 `specs()` 构建 DAG。
- 保证拓扑稳定、缺依赖 fail-fast、环依赖 fail-fast。

### 1.2 读路径（slice）

1) `backend/app/factor_slice_plugin_contract.py`
- 定义读路径插件契约：`FactorSlicePlugin` + `FactorSliceBuildContext`。
- 约束每个插件声明 `factor_name/depends_on` 与 `bucket_specs`，并输出统一 `FactorSliceV1`。

2) `backend/app/factor_slice_plugins.py`
- 默认 `Pivot/Pen/Zhongshu/Anchor` 的 slice 插件实现。
- 每个插件只关心自己的 history/head 组装（pen preview、zhongshu alive、anchor current 等逻辑下沉）。

3) `backend/app/factor_slices_service.py`
- 仅负责读路径调度：加载事件、按 bucket 分组、预取 head、按 `FactorGraph.topo_order` 执行 slice 插件。
- 不再手写 `if factor == ...` 的快照拼装分支，新增因子无需继续膨胀主服务文件。

4) `backend/app/factor_read_freshness.py`
- 统一承载读路径 freshness 门禁（strict / non-strict）：
  - non-strict：可按需触发 freshness ingest；
  - strict：当 `factor_head < aligned_time` 时直接拒绝读取（409）。
- `FactorReadService` 仅做参数编排并委托此模块，避免双实现漂移。

### 1.3 Overlay 渲染路径（draw delta 上游）

1) `backend/app/overlay_orchestrator.py`
- 负责 closed-candle 到 overlay instruction 的增量写入。
- 渲染阶段按插件拓扑顺序执行，不再在 orchestrator 内手写整段 marker/polyline 逻辑。
- 事件归桶改为读取渲染插件的 `bucket_specs` 声明（`factor_name + event_kind -> bucket_name`），新增 overlay 输入时无需再改 orchestrator 分支。
- 输出写入统一为 instruction 流（marker/polyline），不再维护 `pen_def` 专用写入分支。

2) `backend/app/overlay_renderer_plugins.py`
- 默认包含 `overlay.marker` / `overlay.pen` / `overlay.structure` 三类渲染插件。
- 每个插件只负责一类 instruction 构建，并声明自己的 `bucket_specs`；最终由 orchestrator 合并并写入 `OverlayStore`。

### 1.5 Freqtrade 策略适配路径（signal 插件化）

1) `backend/app/freqtrade_adapter_v1.py`
- 负责把 dataframe 与因子 ledger 对齐（写入 candle、触发 factor ingest、校验 ledger freshness）。
- 信号构建改为按插件拓扑调度，不再内联 `pen.confirmed -> tc_enter_long/short` 分支。

2) `backend/app/freqtrade_signal_plugin_contract.py`
- 定义 `FreqtradeSignalPlugin` 契约与 `FreqtradeSignalBucketSpec` 归桶声明。
- 支持每个信号插件声明列初始化逻辑（`prepare_dataframe`）和逐行打标逻辑（`apply`）。

3) `backend/app/freqtrade_signal_plugins.py`
- 默认提供 `signal.pen_direction` 插件，保持当前 `tc_pen_confirmed/tc_pen_dir/tc_enter_long/tc_enter_short` 语义不变。

### 1.6 Draw Delta 自愈校验路径（完整插件化补齐）

1) `backend/app/overlay_integrity_plugins.py`
- 定义 `OverlayIntegrityPlugin` 契约：输入 `factor_slices + latest_overlay_defs`，输出是否触发 overlay 重建。
- 默认插件：
  - `anchor.current.start`：校验 `anchor.head.current_anchor_ref.start_time` 与渲染出的 `anchor.current` 起点一致；
  - `zhongshu.signature`：校验 `zhongshu history/head` 与 `zhongshu.*` 指令集合签名一致。

2) `backend/app/draw_routes.py`
- `/api/draw/delta` 在 `cursor_version_id=0` 首帧读取时，调用 integrity plugins 判定是否需要重建 overlay。
- draw route 不再手写 anchor/zhongshu 具体判定分支，后续新增结构性校验可通过插件追加。

### 1.4 因子目录路径（前端因子开关）

1) `backend/app/factor_catalog.py`
- 基于 `factor_manifest` + `FactorGraph.topo_order` 构建动态因子目录，避免前端硬编码顺序/分组。
- 标准因子目录来自插件 `spec.catalog` 元信息；缺省时回退到 slice bucket 推断。
- `sma` / `signal` 作为前端虚拟分组统一追加。

2) `backend/app/factor_routes.py`
- 新增 `GET /api/factor/catalog`，返回 `GetFactorCatalogResponseV1`。

3) `frontend/src/services/factorCatalog.ts`
- 前端通过接口拉取目录并缓存；接口不可用时降级到本地 fallback，不阻塞图表使用。

### 1.3 统一写链路与读写分离（2026-02-10 新增）

1) `backend/app/pipelines/ingest_pipeline.py`
- 统一 closed-candle 写路径（store -> factor -> overlay -> publish）。
- 覆盖 HTTP ingest、WS ingest、Replay coverage sidecar 计算，减少重复与漂移。
- 当前已作为默认主链路，无 legacy 写路径分支。

2) `backend/app/read_models/factor_read_service.py`
- 统一 factor 读路径时间对齐与 freshness 策略。
- strict 模式下仅读不写，若 factor/overlay 落后返回 `409 ledger_out_of_sync:*`。
- 开关：`TRADE_CANVAS_ENABLE_READ_STRICT_MODE`（默认关闭）。

3) `backend/app/container.py` + `backend/app/flags.py`
- 把装配职责从 `main.py` 下沉到容器层；
- 把主链路高风险开关集中在 `FeatureFlags`，减少散落 `os.environ` 读取。

4) `backend/app/dependencies.py` + `*_routes.py`
- 路由层统一改为 FastAPI `Depends` 显式注入 `runtime/store/read_service`；
- `app.state` 仅作为依赖入口，不再在路由实现中散落读取。

## 2. 标准 factor 的最小能力模型

一个标准 factor 至少包含以下能力：
- `history`（冷）：append-only 事件流，支持全量读取与 at_time 切片读取。
- `head`（热）：支持同一 candle_time 的增量推进与重绘快照。
- 写路径：支持 seed（一次性构建）与 incremental（逐根 closed 增量）一致性。
- 读路径：能在任意 `t` 输出 `history+head` 快照，且不穿透未来数据。
- 绘图联动：能为 overlay/draw delta 提供稳定输入（直接或间接通过已有因子）。
- 特性开关：前端可通过 `sub_feature` 控制可见性；后端新高风险能力默认应有 `TRADE_CANVAS_ENABLE_*` kill-switch。

## 3. 新增 factor 的固定接入面（先去重再插件化后的约束）

### 3.1 必改（固定 4 处）

1) `backend/app/factor_processors.py`
- 新增 `XxxProcessor`，声明 `spec = ProcessorSpec(factor_name="xxx", depends_on=(...))`。
- 实现该因子的事件构造、bootstrap 恢复、head 构造逻辑（按需实现插件钩子）。

2) `backend/app/factor_slice_plugins.py`
- 新增 `XxxSlicePlugin`，完成该因子的 `history/head/meta` 组装。
- 在该插件内声明 `bucket_specs`（`event_kind -> bucket_name`），不再额外维护独立 bucket 配置文件。

3) `backend/app/factor_plugin_contract.py`（或兼容 alias）
- 若新增字段级别插件元信息，先扩展插件契约再落实现。

4) `backend/app/factor_default_components.py`
- 在 `build_default_factor_bundle_specs()` 中挂载 `XxxProcessor + XxxSlicePlugin` 的默认配对。
- 新增 factor 后，orchestrator 与 slices service 通过 manifest 自动生效（无需双处注册）。

### 3.2 按需改（视是否对外可视）

4) `backend/app/overlay_renderer_plugins.py`
- 若该 factor 需要图上展示，新增或扩展对应 overlay renderer，并声明 `bucket_specs`。
- 一般不再修改 `overlay_orchestrator.py`。

5) 前端 `frontend/src/widgets/ChartView.tsx` 及相关 store
- 一般无需手改因子目录常量；仅当新增子特性有特殊交互（非通用可见性逻辑）时才需要接入代码。

6) `backend/app/freqtrade_signal_plugins.py`（按需）
- 若新 factor 需要落地为策略信号列，在此新增 signal plugin；避免直接改 adapter 主流程。

7) `backend/app/overlay_integrity_plugins.py`（按需）
- 若新 factor 引入“overlay 与 factor_slices 一致性”约束，在此新增 integrity plugin；
- 一般不再修改 `draw_routes.py` 的重建判定主流程。

6) 合约文档
- 若新增了外部可见字段/语义，更新 `docs/core/contracts/` 下对应契约。

## 4. 一致性与验收门禁

后端改动（含 factor 算法/装配）至少通过：
- `pytest -q --collect-only`
- `pytest -q`

涉及 core 文档/契约变更时再补：
- `bash docs/scripts/doc_audit.sh`

交付时必须附：
- 命令；
- 关键输出；
- 证据路径（例如 `output/verification/...`）。

## 5. 文档一比一维护要求（Doc Impact）

发生 `feat/fix/refactor` 且触及因子主链路时，至少同步检查：
- `docs/core/factor-modular-architecture.md`（本文件）
- `docs/core/architecture.md`
- `docs/core/contracts/factor_graph_v1.md`
- `docs/core/contracts/factor_sdk_v1.md`
- `docs/core/contracts/factor_v1.md`

原则：代码接入面新增/删除一处，文档的“新增 factor 固定接入面”必须同轮更新。
