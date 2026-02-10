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

2) `backend/app/factor_registry.py`
- `ProcessorSpec` 声明 `factor_name + depends_on`。
- `FactorRegistry` 负责去重、缺失报错、导出 `specs()`。

3) `backend/app/factor_processors.py`
- `PivotProcessor` / `PenProcessor` / `ZhongshuProcessor` / `AnchorProcessor`。
- 每个 processor 只做该因子的领域计算与事件构造。
- `build_default_factor_processors()` 是默认装配入口。

4) `backend/app/factor_graph.py`
- 基于 registry 的 `specs()` 构建 DAG。
- 保证拓扑稳定、缺依赖 fail-fast、环依赖 fail-fast。

### 1.2 读路径（slice）

`backend/app/factor_slices_service.py`
- 从 `FactorStore` 读历史事件和 head snapshot。
- 通过 `build_default_slice_bucket_specs()` 生成事件桶映射，统一归类历史事件。
- `history` 只切片不重算；`head` 优先读存储快照，必要时做有限回补（如 pen preview）。

### 1.3 统一写链路与读写分离（2026-02-10 新增）

1) `backend/app/pipelines/ingest_pipeline.py`
- 统一 closed-candle 写路径（store -> factor -> overlay -> publish）。
- 覆盖 HTTP ingest、WS ingest、Replay coverage sidecar 计算，减少重复与漂移。
- 开关：`TRADE_CANVAS_ENABLE_INGEST_PIPELINE_V2`（默认关闭）。

2) `backend/app/read_models/factor_read_service.py`
- 统一 factor 读路径时间对齐与 freshness 策略。
- strict 模式下仅读不写，若 factor/overlay 落后返回 `409 ledger_out_of_sync:*`。
- 开关：`TRADE_CANVAS_ENABLE_READ_STRICT_MODE`（默认关闭）。

3) `backend/app/container.py` + `backend/app/flags.py`
- 把装配职责从 `main.py` 下沉到容器层；
- 把主链路高风险开关集中在 `FeatureFlags`，减少散落 `os.environ` 读取。

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
- 实现该因子的事件构造与 head 构造逻辑。

2) `backend/app/factor_processors.py`
- 在 `build_default_factor_processors()` 中注册 `XxxProcessor()`。

3) `backend/app/factor_processors.py`
- 在 `build_default_slice_bucket_specs()` 中补充该 factor 的事件桶映射（`event_kind -> bucket_name`）。

4) `backend/app/factor_slices_service.py`
- 组装 `snapshots["xxx"]`（history/head/meta）。

### 3.2 按需改（视是否对外可视）

4) `backend/app/overlay_orchestrator.py`
- 若该 factor 需要图上展示，增加 overlay 构建/增量逻辑。

5) 前端 `frontend/src/widgets/ChartView.tsx` 及相关 store
- 新增/接入 `sub_feature` 可见性开关。

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
