---
title: 第6关：从 RuntimeFlags 到 Container，讲透控制面装配
status: done
created: 2026-02-11
updated: 2026-02-11
---

# 第6关：从 RuntimeFlags 到 Container，讲透控制面装配

前面几关你已经会看“数据面”（candle -> factor -> overlay）。  
这一关我们看“控制面”——系统是怎么在启动时把配置、开关、服务对象安全地装到一起的。

很多线上事故不是算法错，而是控制面失控：

- 同一个功能在 A 机器开着、B 机器关着；
- 某服务偷偷读环境变量，导致行为不可预测；
- 路由直接抓 `app.state.xxx`，改一次全崩。

trade_canvas 这套装配链路，目标就是把这些风险前置消灭。

---

## 0. 先给一句总纲

控制面设计可以记成一句：

**配置只在入口解析一次，能力只在容器里装配一次，运行期只走注入对象，不再读环境。**

这句话就是可回滚、可复现、可测试的根基。

---

## 1. 控制面三层：Settings、FeatureFlags、RuntimeFlags

启动时会读取三种配置对象：

1. `Settings`：路径、CORS、ws catchup limit 等“基础运行参数”。
2. `FeatureFlags`：偏“是否启用”的产品开关（如 strict read、ondemand ingest）。
3. `RuntimeFlags`：偏“怎么运行”的细粒度参数（窗口、并发、补偿、replay、backfill）。

这不是重复设计，而是职责分层：

- `Settings` = 环境底座
- `FeatureFlags` = 产品能力门
- `RuntimeFlags` = 运行口径门

---

## 2. 组合根（Composition Root）：`build_app_container`

`build_app_container` 是整个后端的装配中心。  
它做一件关键事：把所有依赖在启动时显式组装成 `AppContainer`。

核心动作：

- 读取 `flags/runtime_flags`；
- 构建 `CandleStore/FactorStore/OverlayStore`；
- 用 runtime flags 注入 `FactorOrchestrator/OverlayOrchestrator`；
- 构建 read services（factor/draw/world）；
- 构建 market runtime + ingest pipeline + supervisor；
- 最后封成 `AppContainer` 返回。

意义：依赖图可见、可测试、可替换，不靠隐式全局变量。

---

## 3. RuntimeFlags 如何真正影响系统行为（不是摆设）

你可以直接看到它们被注入到关键模块：

- `blocking_workers` -> `configure_blocking_executor(...)`
- `enable_factor_ingest` -> `FactorOrchestrator.ingest_enabled`
- `factor_*` -> `FactorSettings`（pivot/window/lookback/rebuild limit）
- `enable_overlay_ingest` + `overlay_window_candles` -> `OverlaySettings`
- `enable_ingest_compensate_*` -> `IngestPipeline` 补偿策略
- `enable_debug_api` -> debug read path 开关
- `enable_replay_*` -> replay/overlay package 服务门禁

也就是说 flag 不是“写在 env 里看着好看”，而是被结构化注入到每个关键节点。

---

## 4. 单实例一致性：避免“同名服务其实是两套对象”

控制面装配还有个常被忽略的点：**单实例一致性**。

测试会明确校验：

- `runtime.ingest_pipeline is container.ingest_pipeline`
- `runtime.flags is container.flags`
- `runtime.runtime_flags is container.runtime_flags`
- `pipeline._hub is container.hub`

这保证了系统内各模块不是“各自 new 一份”，而是共享同一运行上下文。

---

## 5. 路由层边界：只允许 `app.state.container`

`main.py` 只把一个东西挂进 app state：`container`。  
然后 route 通过 `dependencies.py` 注入服务对象。

对应的边界测试明确禁止：

- 在 route/ws 里直接 `request.app.state.xxx` 到处拿对象；
- 依赖参数写成 optional None；
- 让 route 直接读 env 决策。

这条规则的本质是：  
**路由只管协议转换，不管依赖装配。**

---

## 6. 错误治理边界：ServiceError 在服务层，HTTPException 在路由层

服务层/读模型层统一抛 `ServiceError`，路由层再映射为 HTTP。  
这样做有三个好处：

- 服务层不绑 FastAPI，单测更纯；
- 同类错误可以跨接口复用；
- 协议层变更（HTTP/WS）不污染业务层。

这也是“控制面清晰”的一部分：异常语义先业务化，再传输化。

---

## 7. 运行期模块禁止偷读环境变量（非常关键）

项目里有专门边界测试，禁止这些路径直接读 env：

- read models（world/draw/factor freshness）
- runtime services（ingest/overlay/replay 等）
- infrastructure（`blocking.py`、`ccxt_client.py`）

为什么这么严？

因为一旦运行期任意点偷偷读 env，你就失去了“配置单真源”，  
也失去了“某次请求为何这样行为”的可解释性。

---

## 8. 给你一套“新增运行开关”的安全模板

以后你要加一个新开关，按这 6 步走：

1. 在 `flags.py` 或 `runtime_flags.py` 声明字段与默认值；
2. 在 `build_app_container` 显式注入到目标服务构造参数；
3. 禁止在运行模块内直接 `os.environ` 读取；
4. 在对应测试补“开/关行为断言”；
5. 如涉及读口径，补 strict/non-strict 行为断言；
6. 文档写清默认值、回滚方式、影响面。

这套流程的核心是：**配置变更必须走可追踪链路**。

---

## 9. 代码锚点（按控制面路径阅读）

- `backend/app/config.py`
- `backend/app/flags.py`
- `backend/app/runtime_flags.py`
- `backend/app/container.py`
- `backend/app/market_runtime_builder.py`
- `backend/app/dependencies.py`
- `backend/app/main.py`
- `backend/app/service_errors.py`
- `backend/tests/test_backend_architecture_flags.py`
- `backend/tests/test_app_state_boundary.py`

---

## 10. 过关自测

1. 为什么 runtime 服务里禁止直接读环境变量？  
2. 为什么 `build_app_container` 是控制面核心，而不是 route？  
3. `FeatureFlags` 与 `RuntimeFlags` 的边界怎么区分？  
4. 为什么 `ServiceError -> HTTPException` 映射要放在路由层？  
5. 新增一个高风险能力时，如何保证“一键回滚”可行？

能讲清这 5 个问题，你就真正进入“架构师视角”的控制面思维了。
