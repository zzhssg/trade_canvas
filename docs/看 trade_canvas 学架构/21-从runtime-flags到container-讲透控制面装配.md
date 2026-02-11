---
title: 第21关：从 RuntimeFlags 到 Container，讲透控制面装配
status: done
created: 2026-02-11
updated: 2026-02-11
---

# 第21关：从 RuntimeFlags 到 Container，讲透控制面装配

上一关你学了"前端功能开关怎么分层"。这一关我们翻到后端，看"控制面"——系统是怎么在启动时把配置、开关、服务对象安全地装到一起的。

想象一架客机准备起飞。机长不会边飞边查油量、边飞边调气压。所有参数在起飞前就要确认完毕，写进飞行计划，飞行中只按计划执行。

后端系统也一样。很多线上事故不是算法错，而是控制面失控：

- 同一个功能在 A 机器开着、B 机器关着（飞行员和副驾看的仪表盘不一样）；
- 某服务偷偷读环境变量，导致行为不可预测（飞行中临时改航线）；
- 路由直接抓 `app.state.xxx`，改一次全崩（乘客自己去驾驶舱拨开关）。

trade_canvas 这套装配链路，目标就是把这些风险前置消灭。

---

## 0. 先给一句总纲

控制面设计可以记成一句：

**配置只在入口解析一次，能力只在容器里装配一次，运行期只走注入对象，不再读环境。**

就像飞机的预检清单：起飞前全部确认，起飞后不再翻清单。

---

## 1. 控制面三层：Settings、FeatureFlags、RuntimeFlags

启动时会读取三种配置对象，就像飞行前要确认三类参数：

1. **Settings**：路径、CORS、ws catchup limit 等"基础运行参数"。（机场环境——跑道长度、天气、海拔）
2. **FeatureFlags**：偏"是否启用"的产品开关（如 strict read、ondemand ingest）。（航线许可——这条航线今天飞不飞）
3. **RuntimeFlags**：偏"怎么运行"的细粒度参数（窗口、并发、补偿、replay、backfill）。（飞行参数——巡航高度、油量、速度）

这不是重复设计，而是职责分层：

- `Settings` = 环境底座（不常变）
- `FeatureFlags` = 产品能力门（按版本变）
- `RuntimeFlags` = 运行口径门（可热调）

---

## 2. 组合根（Composition Root）：`build_app_container`

`build_app_container` 是整个后端的装配中心——相当于机长起飞前的最终确认环节。

它做一件关键事：把所有依赖在启动时显式组装成 `AppContainer`。

核心动作：

- 读取 `flags/runtime_flags`；
- 构建 `CandleStore/FactorStore/OverlayStore`；
- 用 runtime flags 注入 `FactorOrchestrator/OverlayOrchestrator`；
- 构建 read services（factor/draw/world）；
- 构建 market runtime + ingest pipeline + supervisor；
- 最后封成 `AppContainer` 返回。

意义：依赖图可见、可测试、可替换，不靠隐式全局变量。就像飞行计划书——每个参数都白纸黑字，不靠机长"凭感觉"。

---

## 3. RuntimeFlags 如何真正影响系统行为

Flags 不是"写在 env 里看着好看"的摆设，而是被结构化注入到每个关键节点：

- `blocking_workers` → `configure_blocking_executor(...)`
- `enable_factor_ingest` → `FactorOrchestrator.ingest_enabled`
- `factor_*` → `FactorSettings`（pivot/window/lookback/rebuild limit）
- `enable_overlay_ingest` + `overlay_window_candles` → `OverlaySettings`
- `enable_ingest_compensate_*` → `IngestPipeline` 补偿策略
- `enable_debug_api` → debug read path 开关
- `enable_replay_*` → replay/overlay package 服务门禁

每个 flag 都有明确的注入目标，就像飞行参数表里每一项都对应具体的仪表盘读数。

---

## 4. 单实例一致性：避免"同名服务其实是两套对象"

控制面装配还有个常被忽略的点：**单实例一致性**。

测试会明确校验：

- `runtime.ingest_pipeline is container.ingest_pipeline`
- `runtime.flags is container.flags`
- `runtime.runtime_flags is container.runtime_flags`
- `pipeline._hub is container.hub`

这保证了系统内各模块不是"各自 new 一份"，而是共享同一运行上下文。

类比飞行：机长和副驾必须看同一套仪表盘，不能各看各的。如果两人看到的油量不一样，迟早出事。

---

## 5. 路由层边界：只允许 `app.state.container`

`main.py` 只把一个东西挂进 app state：`container`。
然后 route 通过 `dependencies.py` 注入服务对象。

对应的边界测试明确禁止：

- 在 route/ws 里直接 `request.app.state.xxx` 到处拿对象；
- 依赖参数写成 optional None；
- 让 route 直接读 env 决策。

这条规则的本质是：
**路由只管协议转换，不管依赖装配。**——乘客只管点餐，不许进驾驶舱拨开关。

---

## 6. 错误治理边界：ServiceError 在服务层，HTTPException 在路由层

服务层/读模型层统一抛 `ServiceError`，路由层再映射为 HTTP。
这样做有三个好处：

- 服务层不绑 FastAPI，单测更纯；
- 同类错误可以跨接口复用；
- 协议层变更（HTTP/WS）不污染业务层。

这也是控制面清晰的一部分：异常语义先业务化，再传输化。就像飞行中的故障代码——机组内部用标准代码沟通，对乘客只说"我们遇到了轻微气流"。

---

## 7. 运行期模块禁止偷读环境变量

项目里有专门边界测试，禁止这些路径直接读 env：

- read models（world/draw/factor freshness）
- runtime services（ingest/overlay/replay 等）
- infrastructure（`blocking.py`、`ccxt_client.py`）

为什么这么严？

因为一旦运行期任意点偷偷读 env，你就失去了"配置单真源"，也失去了"某次请求为何这样行为"的可解释性。

类比飞行：如果副驾可以不经机长同意就改航线参数，黑匣子里的记录就没法还原真实决策链。

---

## 8. 给你一套"新增运行开关"的安全模板

以后你要加一个新开关，按这 6 步走：

1. 在 `flags.py` 或 `runtime_flags.py` 声明字段与默认值；
2. 在 `build_app_container` 显式注入到目标服务构造参数；
3. 禁止在运行模块内直接 `os.environ` 读取；
4. 在对应测试补"开/关行为断言"；
5. 如涉及读口径，补 strict/non-strict 行为断言；
6. 文档写清默认值、回滚方式、影响面。

这套流程的核心是：**配置变更必须走可追踪链路**——就像每次改飞行计划都要签字存档。

---

## 9. 这套设计背后的通用方法论

你可以把控制面装配抽象成一套通用模板：

1. **配置分层**：环境底座、功能开关、运行参数各司其职，不混在一起。
2. **单点装配**：所有依赖在一个组合根里显式组装，不散落在各模块。
3. **注入优先**：运行期模块只消费注入结果，禁止自行读取外部状态。
4. **单实例一致**：同一运行上下文内，同名服务必须是同一对象。
5. **边界测试守护**：用测试钉死"谁能访问什么"，防止越层访问。

这套模板不只适合量化系统——微服务网关、任务调度器、IoT 设备管理，凡是有"配置 → 装配 → 运行"三阶段的系统都通用。

---

## 10. 代码锚点（按控制面路径阅读）

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

## 11. 过关自测

1. 为什么 runtime 服务里禁止直接读环境变量？
2. 为什么 `build_app_container` 是控制面核心，而不是 route？
3. `FeatureFlags` 与 `RuntimeFlags` 的边界怎么区分？
4. 为什么 `ServiceError → HTTPException` 映射要放在路由层？
5. 新增一个高风险能力时，如何保证"一键回滚"可行？

能讲清这 5 个问题，你就真正进入"架构师视角"的控制面思维了。
