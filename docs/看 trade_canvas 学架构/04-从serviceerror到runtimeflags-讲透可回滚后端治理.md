---
title: 第4关：从 ServiceError 到 RuntimeFlags，讲透可回滚后端治理
status: done
created: 2026-02-11
updated: 2026-02-11
---

# 第4关：从 ServiceError 到 RuntimeFlags，讲透可回滚后端治理

前面三关你学的是“算法与插件协同”。  
这一关我们换一个更工程化、也更现实的问题：

**系统能不能在“持续迭代 + 持续上线”下，依然可控、可回滚、可排障？**

这不是锦上添花，而是后端成熟度分水岭。

---

## 0. 先给一句总纲：可回滚架构 = 错误分层 + 配置单真源 + kill-switch + 关停可观测

你可以把这套治理当成四层保险：

1. 错误分层：业务层不直接绑框架异常。
2. 配置单真源：运行期开关只能从统一入口注入。
3. kill-switch：高风险能力默认关，必要时一键熔断。
4. 关停可观测：停服务时也尽量“有秩序”，减少噪音与误报。

这四层合起来，才叫“可回滚”而不是“碰运气”。

---

## 1. 第一层保险：错误分层，先把“业务错误”和“HTTP 传输”拆开

很多项目会在 service 里直接 `raise HTTPException`。  
短期快，长期会出现两个问题：

- 业务层被 FastAPI 绑死，单测要跟着框架跑。
- 同一类业务错误在不同 route 里表达不一致，前端难处理。

trade_canvas 现在改成：

- service/read-model 抛 `ServiceError`
- route 层统一 `to_http_exception()` 映射

这等于把“业务语义”和“传输协议”做了边界隔离。

你只需要记住一句：

**service 负责“错了什么”，route 负责“怎么回给 HTTP”。**

---

## 2. 第二层保险：配置单真源，避免运行期散读 env

另一个常见坑：  
代码到处 `os.environ`，今天改一处生效、明天另一处忘改，行为漂移非常难查。

现在的治理口径是：

- `RuntimeFlags` 统一读取 env
- `container` 启动时注入
- runtime/service 只消费注入结果，不再临时读环境变量

这件事看起来“只是整洁”，实际收益非常大：

1. 行为可复现：同一组 flags 就是同一行为。
2. 测试可控：单测不需要到处 monkeypatch env。
3. 变更可审计：开关都在同一个结构体里看得见。

你可以把它类比 C 里的做法：  
不是到处读全局宏，而是在初始化阶段把配置灌进 context，后续只读 context。

---

## 3. 第三层保险：kill-switch 先行，尤其是补偿类逻辑

最容易“救火变事故”的地方，是补偿逻辑。  
例如 ingest 主链里，overlay 失败后要不要补偿重置？新写入 candle 要不要回滚？

这里采用了标准策略：

- 能改变主链路语义的能力都要有 `TRADE_CANVAS_ENABLE_*`
- 默认关闭
- 逐步放开

你可以把这理解成“软回滚开关”：

- 功能异常时，不必立刻回滚代码；
- 先关开关，恢复主链稳定；
- 再离线修复与复盘。

这就是工程里常说的“把风险隔离在可操作面”。

---

## 4. 第四层保险：服务关停也要有秩序

很多人只关注“运行时成功路径”，忽略“关停路径”。  
结果是 E2E 虽然通过，但日志全是 `CancelledError`，难以分辨真假问题。

本仓现在做了两层收口：

1. 应用层：在 shutdown 阶段对被取消的 HTTP 请求做受控响应（503），减少无意义异常栈。
2. 脚本层：E2E cleanup 改成“先 TERM + 等待，再必要时 KILL”，减少残留进程与收尾抖动。

注意这不是“掩盖问题”，而是把“预期中的取消”从“异常噪音”变成“可解释行为”。

---

## 5. 这套治理为什么对初学者也重要

你可能会想：我先把算法写对不就行了？

答案是：**算法正确只是第一步，可控迭代才是长期能力。**

当你进入多人协作和持续交付后，真正拖垮项目的往往不是“公式写错”，而是：

- 错误边界混乱
- 配置来源混乱
- 紧急回滚手段缺失
- 关停阶段不可观测

这关学会后，你会从“能写功能”进化为“能守住系统”。

---

## 6. 代码锚点（按治理链路）

- 错误分层
  - `backend/app/service_errors.py`
  - `backend/app/market_http_routes.py`
  - `backend/app/backtest_routes.py`
- 配置单真源
  - `backend/app/runtime_flags.py`
  - `backend/app/container.py`
  - `backend/app/market_runtime_builder.py`
- kill-switch 与补偿
  - `backend/app/pipelines/ingest_pipeline.py`
  - `backend/app/market_ingest_service.py`
- 关停治理
  - `backend/app/shutdown_cancellation_middleware.py`
  - `backend/app/main.py`
  - `scripts/e2e_acceptance.sh`
- 回归护栏
  - `backend/tests/test_app_state_boundary.py`
  - `backend/tests/test_runtime_flags.py`
  - `backend/tests/test_shutdown_cancellation_middleware.py`

---

## 7. 过关自测（你应能脱稿讲清）

1. 为什么 service 里直接抛 `HTTPException` 会在长期演进时变成负担？
2. `RuntimeFlags` 集中注入相对散读 env 的核心收益是什么？
3. 为什么补偿逻辑必须先有 kill-switch，且默认关闭？
4. shutdown 阶段把 `CancelledError` 变成受控 503，解决的是哪类工程问题？
5. 如果线上出现 ingest 侧异常，你的“最短止血路径”应如何设计？

你如果能把这五题讲顺，第 4 关就过了。
