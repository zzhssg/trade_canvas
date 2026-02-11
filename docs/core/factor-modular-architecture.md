---
title: Factor 模块化架构
status: done
created: 2026-02-02
updated: 2026-02-11
---

# Factor 模块化架构

本文聚焦 factor 链路的三个问题：
- 写链路如何保持单路径且可复现；
- 读链路如何保持插件化且可扩展；
- 新增 factor 时最小改动面是什么。

---

## 1. 当前模块分层

### 1.1 写链路核心

- `backend/app/factor_orchestrator.py`
  - 负责 ingest 调度、状态推进、事件写入。
- `backend/app/factor_tick_executor.py`
  - 负责每个 tick 的插件执行顺序与状态衔接。
- `backend/app/factor_ingest_window.py`
  - 负责窗口规划（读取起点/批次/process_times）。
- `backend/app/factor_rebuild_loader.py`
  - 负责历史事件回放与 bootstrap。
- `backend/app/factor_fingerprint.py`
  - 负责逻辑指纹生成。
- `backend/app/factor_fingerprint_rebuild.py`
  - 负责指纹不匹配时的 trim+clear+rebuild 闸门。

### 1.2 插件注册与拓扑

- `backend/app/factor_plugin_contract.py`
  - 统一 `FactorPluginSpec`（`factor_name` / `depends_on`）。
- `backend/app/factor_plugin_registry.py`
  - 注册、去重、缺依赖与环依赖 fail-fast。
- `backend/app/factor_graph.py`
  - 生成稳定拓扑序，作为写读两侧统一执行顺序。
- `backend/app/factor_default_components.py`
  - 默认 processor 与 slice plugin 的单点挂载。
- `backend/app/factor_manifest.py`
  - 启动时校验读写插件一致性。

### 1.3 读链路核心

- `backend/app/factor_slice_plugin_contract.py`
- `backend/app/factor_slice_plugins.py`
- `backend/app/factor_slices_service.py`
- `backend/app/read_models/factor_read_service.py`
- `backend/app/factor_read_freshness.py`

读链路语义：
- 按 `aligned_time` 读，不穿透未来。
- strict 模式下只读不修复，缺新鲜度返回 409。

### 1.4 与 overlay/world 的耦合边界

- `backend/app/factor_head_builder.py`
  - 统一 pen/zhongshu head 组装，避免读写两套规则漂移。
- `backend/app/overlay_integrity_plugins.py`
  - draw 首帧可基于 factor slices 做一致性检查。
- `backend/app/read_models/world_read_service.py`
  - 强制 factor/draw candle_id 对齐。

---

## 2. 运行时配置口径

- 配置真源：`backend/app/runtime_flags.py`
- 注入点：`backend/app/container.py`

当前 factor 关键参数：
- `enable_factor_ingest`
- `enable_factor_fingerprint_rebuild`
- `factor_pivot_window_major`
- `factor_pivot_window_minor`
- `factor_lookback_candles`
- `factor_state_rebuild_event_limit`
- `factor_rebuild_keep_candles`
- `factor_logic_version_override`

原则：
- factor 运行参数在启动期统一注入。
- service/orchestrator 不再散读 env。

---

## 3. 写链路执行模型

```mermaid
flowchart LR
  A["CandleStore closed bars"] --> B["FactorOrchestrator ingest_closed"]
  B --> C["FactorIngestWindow plan"]
  C --> D["FactorTickExecutor run"]
  D --> E["Processor Plugins"]
  E --> F["FactorStore append history/head"]
```

不变量：
1. 只处理 closed candles。
2. 同一窗口同一输入得到同一输出。
3. 指纹变化必须触发重建闸门，禁止静默复用旧产物。

---

## 4. 读链路执行模型

```mermaid
flowchart LR
  A["GET /api/factor/slices"] --> B["FactorReadService"]
  B --> C["resolve aligned_time"]
  C --> D["FactorSlicesService"]
  D --> E["Slice Plugins by topo_order"]
  E --> F["GetFactorSlicesResponseV1"]
```

不变量：
1. 响应 `candle_id` 必须等于 `{series_id}:{aligned_time}`。
2. strict 模式下不触发隐式 ingest。
3. 插件输出通过统一 schema 聚合，避免 route 层拼 JSON。

---

## 5. 新增 Factor 的最小接入面

必改项：
1. `backend/app/factor_processor_*.py`
   - 新增算法 processor（含 `spec` 与领域事件产出）。
2. `backend/app/factor_slice_plugins.py`
   - 新增对应 slice plugin（history/head/meta 输出）。
3. `backend/app/factor_default_components.py`
   - 挂载 processor + slice plugin 对。
4. `docs/core/contracts/factor_*.md`
   - 更新契约与字段语义。

按需改：
- `backend/app/overlay_renderer_plugins.py`（需要图上呈现时）
- `backend/app/freqtrade_signal_plugins.py`（需要策略信号列时）
- `backend/app/overlay_integrity_plugins.py`（需要额外一致性校验时）

---

## 6. 验收与回滚

最小门禁：

```bash
pytest -q
```

涉及核心文档时：

```bash
bash docs/scripts/doc_audit.sh
```

回滚策略：
- 参数/能力异常：优先通过 `TRADE_CANVAS_ENABLE_*` 开关快速熔断。
- 代码缺陷：按原子提交 `git revert <sha>` 回退。

---

## 7. 已移除的历史做法

- 在 `FactorOrchestrator` 内手写大量 `if factor == ...` 分支。
- 读链路与写链路分别维护一套 pen/zhongshu head 组装逻辑。
- 运行期在多个模块散落读取 env 并直接参与调度。
