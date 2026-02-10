---
title: Factor Plugin Contract v1（因子插件契约）
status: draft
created: 2026-02-10
updated: 2026-02-10
---

# Factor Plugin Contract v1（因子插件契约）

目标：把“新增因子”的接入点从手工散落改为统一插件声明，确保可扩展、可回滚、可验收。

## 1. 最小插件规格

```python
@dataclass(frozen=True)
class FactorCatalogSubFeatureSpec:
    key: str
    label: str
    default_visible: bool = True

@dataclass(frozen=True)
class FactorCatalogSpec:
    label: str | None = None
    default_visible: bool = True
    sub_features: tuple[FactorCatalogSubFeatureSpec, ...] = ()

@dataclass(frozen=True)
class FactorPluginSpec:
    factor_name: str
    depends_on: tuple[str, ...] = ()
    catalog: FactorCatalogSpec | None = None
```

约束：
- `factor_name` 必须非空且稳定；
- `depends_on` 只能引用已注册插件；
- 同一运行时内 `factor_name` 不可重复。
- `catalog` 用于声明前端因子面板元信息（label/default/sub_feature）；缺省时可由读路径 bucket 回退生成。

## 2. 运行时注册接口

```python
class FactorPluginRegistry:
    def __init__(self, plugins: list[FactorPlugin]) -> None: ...
    def get(self, factor_name: str) -> FactorPlugin | None: ...
    def require(self, factor_name: str) -> FactorPlugin: ...
    def plugins(self) -> tuple[FactorPlugin, ...]: ...
    def specs(self) -> tuple[FactorPluginSpec, ...]: ...
```

错误语义：
- 空名：`empty_factor_name`
- 重名：`duplicate_factor:<name>`
- 缺失：`missing_factor:<name>`

## 3. 写路径执行接口（Tick Plugin）

写路径（`FactorOrchestrator`）按 `FactorGraph.topo_order` 调用插件 `run_tick(...)`：

```python
class FactorTickPlugin(FactorPlugin, Protocol):
    def run_tick(self, *, series_id: str, state: Any, runtime: dict[str, Any]) -> None: ...
```

约束：
- 所有写路径插件必须实现 `run_tick`，缺失时运行时 fail-fast（`factor_missing_run_tick:<factor>`）；
- `state` 只允许就地更新当前 tick 的增量状态，不得读取未来 candle；
- `runtime` 用于跨插件共享只读能力（例如 anchor 评估器），避免在 orchestrator 手写因子分支。

## 4. 写路径恢复与 Head 钩子（Bootstrap + Head Snapshot）

为消除 orchestrator 里的因子硬编码，插件可选实现以下恢复/快照钩子：

```python
class FactorBootstrapPlugin(FactorTickPlugin, Protocol):
    def collect_rebuild_event(self, *, kind: str, payload: dict[str, Any], events: list[dict[str, Any]]) -> None: ...
    def sort_rebuild_events(self, *, events: list[dict[str, Any]]) -> None: ...
    def bootstrap_from_history(self, *, series_id: str, state: Any, runtime: dict[str, Any]) -> None: ...

class FactorHeadSnapshotPlugin(FactorTickPlugin, Protocol):
    def build_head_snapshot(self, *, series_id: str, state: Any, runtime: dict[str, Any]) -> dict[str, Any] | None: ...
```

语义：
- `collect_rebuild_event/sort_rebuild_events`：定义该因子如何从历史事件回放恢复 bootstrap 输入；
- `bootstrap_from_history`：在拓扑序下恢复该因子的热状态（仅使用 `<=head_time` 数据）；
- `build_head_snapshot`：在写路径结束时产出该因子 head，返回 `None` 表示本轮不落 head。

## 5. 与旧接口兼容

当前仍保留 `FactorRegistry` / `ProcessorSpec` 兼容别名，避免一次性切断存量调用；
后续阶段逐步替换为 `FactorPluginRegistry` / `FactorPluginSpec`。

## 6. 读路径插件扩展（Slice Plugin）

写路径插件化后，读路径（`/api/factor/slices`）补充同构插件接口：

```python
@dataclass(frozen=True)
class FactorSliceBuildContext:
    series_id: str
    aligned_time: int
    start_time: int
    window_candles: int
    candle_id: str
    buckets: Mapping[str, list[dict]]
    head_rows: Mapping[str, FactorHeadSnapshotRow | None]
    snapshots: Mapping[str, FactorSliceV1]

class FactorSlicePlugin(Protocol):
    spec: FactorPluginSpec
    bucket_specs: tuple[SliceBucketSpec, ...]
    def build_snapshot(self, ctx: FactorSliceBuildContext) -> FactorSliceV1 | None: ...
```

约束：
- `spec.factor_name/depends_on` 与写路径保持同名同依赖，读写拓扑必须一致；
- `bucket_specs` 负责声明事件归桶，不允许在 `FactorSlicesService` 手写散落分支；
- `build_snapshot` 只消费 `<= aligned_time` 的数据，不得穿透未来；
- 若插件返回 `None`，表示该因子在当前窗口不可见（与旧 `factors[]` 语义一致）。

## 7. 统一装配（Manifest）

为了让写路径与读路径不再各自维护默认注册列表，引入 Manifest：

```python
@dataclass(frozen=True)
class FactorManifest:
    processors: tuple[FactorProcessor, ...]
    slice_plugins: tuple[FactorSlicePlugin, ...]

def build_default_factor_manifest() -> FactorManifest: ...
```

约束：
- `processors` 与 `slice_plugins` 的因子集合必须完全相同；
- 同名因子的 `depends_on` 必须完全相同；
- 违反时启动即 fail-fast（`manifest_*` 错误码）。

## 8. 下游插件协同（Overlay / Freqtrade）

当主链路因子插件化后，下游消费链路也应遵循同样的“声明 bucket，再由 orchestrator 调度”原则：

1) Overlay 渲染插件（`overlay_renderer_plugins.py`）
- 插件声明：
  - `spec: FactorPluginSpec`
  - `bucket_specs: tuple[OverlayEventBucketSpec, ...]`
  - `render(ctx) -> OverlayRenderOutput`
- `OverlayOrchestrator` 只负责：
  - 聚合所有 renderer 的 `bucket_specs`；
  - 统一归桶并按拓扑调度；
  - 合并并落盘绘图指令。

2) Freqtrade signal 插件（`freqtrade_signal_plugins.py`）
- 插件声明：
  - `spec: FactorPluginSpec`
  - `bucket_specs: tuple[FreqtradeSignalBucketSpec, ...]`
  - `prepare_dataframe(df)` + `apply(ctx)`
- `annotate_factor_ledger()` 只负责：
  - 因子账本对齐与 freshness 校验；
  - 统一归桶并按拓扑调度 signal plugin；
  - 避免在 adapter 主流程里写死某个因子（如 `pen.confirmed`）。

3) Draw Delta integrity 插件（`overlay_integrity_plugins.py`）
- 插件声明：
  - `name: str`
  - `evaluate(ctx) -> OverlayIntegrityResult`
- `draw_routes` 只负责：
  - 在 `cursor_version_id=0` 读取首帧时执行 integrity plugins；
  - 依据插件结论触发 `overlay_orchestrator` 重建；
  - 避免在 `draw_routes.py` 中长期累积按 feature 手写判定分支。

## 9. 验收门禁

- `pytest -q backend/tests/test_factor_plugin_registry.py backend/tests/test_factor_manifest.py backend/tests/test_factor_slice_plugins.py backend/tests/test_factor_registry.py backend/tests/test_factor_graph.py`
- `pytest -q backend/tests/test_overlay_renderer_plugins.py backend/tests/test_overlay_integrity_plugins.py backend/tests/test_freqtrade_adapter_v1.py`
- `pytest -q`
- `bash docs/scripts/doc_audit.sh`
