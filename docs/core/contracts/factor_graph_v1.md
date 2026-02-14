---
title: Factor Graph Contract v1（因子拓扑与调度）
status: done
created: 2026-02-02
updated: 2026-02-14
---

# Factor Graph Contract v1（因子拓扑与调度）

目标：把“因子依赖拓扑（pivot→pen→zhongshu…）+ 调度顺序 + 可复现不变量”固化为 **可实现、可测试** 的最小契约，避免各处隐式装配导致漂移。

关联契约：
- 因子数据外壳与冷热语义：`docs/core/contracts/factor_v1.md`
- 因子插件注册：`docs/core/contracts/factor_plugin_v1.md`
- 策略消费边界（fail-safe 对齐）：`docs/core/contracts/strategy_v1.md`
- K 线主键/坐标：`docs/core/market-kline-sync.md`
- 当前实现总览：`docs/core/factor-modular-architecture.md`

## 1. 名词

- `factor_name`：因子稳定 key（例如 `pivot`/`pen`/`zhongshu`）。
- `depends_on`：因子拓扑依赖（按 `factor_name` 指向上游）。
- `roots`：一个策略/一个产物链路声明的“需要的因子根集合”（系统必须按依赖闭包补齐）。
- `deps_snapshot`：在 `at_time` 时刻，上游因子对下游暴露的只读快照集合（见 `factor_v1`）。

## 2. 图结构（DAG 强约束）

### 2.1 图定义

给定一组因子规格 `FactorSpecV1[]`（见 `factor_v1`），构造有向图：

- 节点：`factor_name`
- 边：`factor_name -> depends_on[*]`

### 2.2 必须满足

- **无环（DAG）**：检测到 cycle 必须拒绝启动/拒绝注册（返回可定位的错误信息：cycle path）。
- **依赖闭包完整**：若 `roots` 引用的因子缺失，或其依赖缺失，必须 fail-fast（拒绝计算），而不是“缺哪个算哪个”。
- **稳定拓扑序**：对同一组因子，拓扑排序必须确定性（例如按 `factor_name` 做 tie-break），避免同输入不同输出。

## 3. 调度语义（closed-candle 增量）

### 3.1 驱动输入（唯一权威）

因子引擎只允许由 `CandleClosed` 驱动（forming 不进入引擎、不落因子账本），详见 `docs/core/source-of-truth.md` 与 `market-kline-sync`。

### 3.2 每根收线的执行顺序

在同一根 `candle_time=t` 的一次 `apply_closed()` 内：

1) 引擎按拓扑序依次执行各因子 `apply_closed(t)`（或等价接口）。
2) 对于某个因子 `F`：
   - 其可读依赖仅来自 `deps_snapshot`（上游因子在同一 `t` 的输出快照）。
   - 禁止在切片/输出阶段“回调依赖因子的 slice_at()/compute()”。

> 解释：这样做把“计算顺序”收敛到单一真源（FactorGraph），避免递归切片/重复计算/未来函数风险。

### 3.3 计算与切片的边界

- `apply_closed(t)`：写路径（增量推进 + 落盘），允许产生：
  - history append events（冷）
  - head snapshot（热，短窗态）
  -（可选）overlay/indicator/strategy 的派生产物（应通过二级 delta ledger 同源化）
- `slice_at(t)`：读路径（构造快照），必须满足：
  - history：纯切片（仅过滤/二分/截断），禁止重算（`seed ≡ incremental` 的核心保障）
  - head：允许短窗重算，但只能使用 `<=t` 的输入；若有 hot ledger，则优先读 hot ledger 的点查快照

## 4. 最小回归门禁（必须可自动化）

建议至少具备以下“能失败的”保护：

1) DAG 校验：人为构造 cycle，注册时必须失败（并输出 cycle path）。
2) 确定性：同一份输入 `CandleClosed` 序列跑两次（新 DB），输出 `latest_ledger.candle_id` 与关键事件条数一致。
3) 依赖一致性：下游（例如 `pen`）的输出必须引用上游（例如 `pivot`）在同一 `at_time` 的快照；若 `deps_snapshot` 缺失或 `at_time` 不一致，必须 fail-safe（拒绝出信号/拒绝写 delta）。

## 5. 运行时绑定（2026-02）

当前后端实现对应关系：
- 注册中心：`backend/app/factor/registry.py`
- Tick 插件集合：`backend/app/factor/default_components.py` + `backend/app/factor/bundles/*.py`
- 统一装配清单：`backend/app/factor/manifest.py`
- DAG 构建：`backend/app/factor/graph.py`
- 调度入口：`backend/app/factor/orchestrator.py`
- 读路径插件：`backend/app/factor/slice_plugins.py`
- 读路径调度：`backend/app/factor/slices_service.py`

要求：
- 默认运行时必须从同一份 manifest 同时注入写路径 tick_plugins 与读路径 slice_plugins，不允许两份手工列表长期分叉。
- 因子拓扑必须由 registry 的 `specs()` 生成，不允许在 orchestrator 重复手写一份依赖图。
- 写路径 bootstrap/head 也必须按同一拓扑执行插件钩子（`bootstrap_from_history` / `build_head_snapshot`），避免重建逻辑漂移。
- 新增 factor 时，`FactorPluginSpec` 与 DAG 结果必须在测试中可验证（例如 topo_order 包含新增节点且顺序稳定）。
- 与拓扑对应的读路径组装应通过 `FactorSlicePlugin` 统一声明（`bucket_specs + build_snapshot`），避免写路径新增后读路径漏接入。
