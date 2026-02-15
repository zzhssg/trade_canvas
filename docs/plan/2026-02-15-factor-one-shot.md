---
title: Factor 能力清单一体化架构（One-shot）
status: 已完成
owner: codex
created: 2026-02-15
updated: 2026-02-15
---

## 背景

- 当前因子主链路（`candles -> factor -> overlay -> world`）可工作，但新增因子时仍存在多处散点改动：写链路状态模型、overlay 默认插件列表、replay 前端因子硬编码拼装、freqtrade adapter 职责过重。
- 真实诉求：在保持现有链路稳定的前提下，实现“同源数据 + 读写分离 + 新增因子低改动 + 一次声明可接入回测/实盘/绘图/回放”。
- 用户决策（本计划已锁定）：
  1. `feature` 采用宽表快照（A）
  2. 一致性采用强一致门禁（A）
  3. freqtrade live/backtest 共用同一 feature 协议（A）
  4. 新增因子默认仅接入安全链路，风险链路显式开启（A）

## 目标 / 非目标

- 目标
  - 引入 `capability manifest`：新增因子默认只接 `factor/read/replay`，`overlay/feature/backtest/freqtrade` 显式启用。
  - 新增 `feature` 物化层（宽表快照），并让 freqtrade live/backtest 统一消费该协议。
  - 回放与回测包编译从“硬编码因子分支”收敛为“基于契约/能力清单的通用编译”。
  - 保持 closed candle 唯一真源、保持读写分离、保持强一致门禁。
- 非目标
  - 不重写已有 pivot/pen/zhongshu/anchor/sr 算法语义。
  - 不做多进程分布式任务平台改造（保留单体内调度器）。
  - 不引入兼容双轨，不保留“旧入口 + 新入口”并行。

## 约束 / 边界（必填）

- 业务/技术约束：
  - closed candle 为唯一权威输入；forming 不进入 factor/feature/strategy 计算。
  - 数据流必须单向：`ingest -> store -> factor -> overlay/feature -> read_model -> route`。
  - 强一致门禁：同一 `aligned_time` 下任一产物缺失即拒绝读取，不做隐式补算。
- 不可变契约（Schema/API/字段口径）：
  - `GetFactorSlicesResponseV1`、`DrawDeltaV1`、`WorldStateV1` 对外字段不破坏性改名。
  - freqtrade adapter 对外 `annotate_factor_ledger(...)` 入口保持可用，内部切换为 feature 协议消费。
- 目录边界（涉及目录 + 是否跨边界）：
  - 跨边界（高风险）：`backend/app/factor`、`backend/app/overlay`、`backend/app/freqtrade`、`backend/app/backtest`、`backend/app/replay`、`backend/app/read_models`、`frontend/src/widgets/chart`、`docs/core`、`docs/plan`。
- 开关/灰度策略（`VITE_ENABLE_*` / `TRADE_CANVAS_ENABLE_*`）：
  - 新增：`TRADE_CANVAS_ENABLE_FEATURE_INGEST`（默认 `1`）、`TRADE_CANVAS_ENABLE_FEATURE_STRICT_READ`（默认 `1`）。
  - capability 开关按因子粒度放在 manifest，不新增每因子 env 开关，避免配置爆炸。

## 成功指标（可量化，必填）

- 指标 1：新增一个“仅 factor 层”因子时，生产代码改动不超过 3 个文件（`processor + bundle + 测试`），且无需改 orchestrator 主流程。
- 指标 2：新增一个“接入 overlay+feature+freqtrade”因子时，除 `processor + bundle` 外，仅新增/修改 `capability manifest` 与对应插件文件，不改中心注册列表。
- 指标 3：强一致门禁生效：故意制造 `feature/overlay` 滞后时，相关读口返回 `409 ledger_out_of_sync:*`。
- 证据命令与产物路径：
  - `pytest -q`
  - `cd frontend && npm install && npm run build`
  - `bash scripts/quality_gate.sh && bash scripts/e2e_acceptance.sh`
  - 产物：`output/playwright/`、测试日志、必要时 sqlite 快照查询输出。

## YAGNI / 本轮明确不做（必填）

- 本轮不做：
  - 不建设外部 MQ/Kafka 调度系统；
  - 不做多租户多集群编排；
  - 不做全量历史重算服务化。
- 不做原因：
  - 当前目标是降低新增因子改动面与耦合，不是扩展部署形态。
- 重新评估触发条件：
  - 单机调度吞吐无法满足（持续出现主链路超时）；
  - 包构建作业积压影响在线读写稳定性。

## 方案概述

- 方案 A（采用）：单体内“多编译器 + 能力清单 + 强一致门禁”
  - 编译器链路：
    - `factor compiler`：candle -> factor ledger
    - `overlay compiler`：factor ledger -> overlay ledger
    - `feature compiler`：factor ledger -> feature ledger（宽表）
    - `package compiler`：feature/overlay -> backtest package / replay package
  - 调度分层：
    - 主链路同步编排（每根 closed candle 触发，强一致）
    - 后台作业调度（回放包/回测包/覆盖率构建）
  - capability manifest 控制因子接入面，默认安全接入，风险接入显式声明。
- 方案 B（备选，不采用）：拆多服务 + 事件总线
  - 优点：服务边界硬隔离。
  - 缺点：回滚与验收成本高，超出当前迭代目标。
- 取舍依据：
  - 契约稳定性：A 不破坏现有 API 主契约。
  - 回滚成本：A 支持原子提交逐步 `git revert`。
  - 验收成本：A 可复用现有 pytest + e2e 门禁。

## 里程碑

- M0（架构契约）
  - 落盘 capability manifest 与 feature 协议文档，明确默认接入策略与强一致规则。
- M1（factor 内核去耦）
  - 引入通用插件状态槽位，减少对内建因子字段的硬编码耦合。
- M2（feature 编译层）
  - 新增 feature store/orchestrator/read_service；接入主链路编排与强一致门禁。
- M3（downstream 接入）
  - freqtrade live/backtest 改为统一消费 feature 协议；新增 backtest package 编译层。
- M4（replay/overlay 通用化）
  - replay package 输出因子 schema 元信息；前端回放去因子名硬编码拼装。
- M5（验收与文档收口）
  - 通过质量门禁、E2E 门禁，更新 `docs/core` 契约与 runbook。

## 任务拆解

- [x] 步骤 1：能力清单与契约骨架
  - 改什么：新增 `backend/app/factor/capability_manifest.py`、`backend/app/feature/contracts.py`；更新 `docs/core/contracts` 相关文档。
  - 怎么验收：`pytest -q --collect-only`；`bash docs/scripts/doc_audit.sh`
  - 怎么回滚：`git revert <step1_sha>`
  - 删什么：删除文档中“新增因子需改中心注册列表”的旧描述
- [x] 步骤 2：feature 编译层与主链路接线
  - 改什么：新增 `backend/app/feature/store.py`、`backend/app/feature/orchestrator.py`、`backend/app/feature/read_service.py`；修改 `backend/app/pipelines/ingest_pipeline*.py`
  - 怎么验收：`pytest -q backend/tests/test_factor_orchestrator_settings.py backend/tests/test_world_read_service.py`
  - 怎么回滚：`git revert <step2_sha>`
  - 删什么：adapter 内直接拼装 feature 的旧逻辑
- [x] 步骤 3：freqtrade/backtest 统一 feature 协议
  - 改什么：修改 `backend/app/freqtrade/adapter_v1.py`、新增 `backend/app/backtest/package_builder.py`、更新 backtest 服务接线
  - 怎么验收：`pytest -q backend/tests/test_freqtrade_adapter_v1.py backend/tests/test_backtest_api.py`
  - 怎么回滚：`git revert <step3_sha>`
  - 删什么：freqtrade adapter 中直接消费 factor event 的硬编码分支
- [x] 步骤 4：overlay/replay 通用化与前端去硬编码
  - 改什么：修改 `backend/app/overlay/renderer_plugins.py`、`backend/app/replay/package_builder_v1.py`、`frontend/src/widgets/chart/replayFactorSlices.ts`
  - 怎么验收：`pytest -q backend/tests/test_replay_package_v1.py backend/tests/test_overlay_renderer_plugins.py`；`cd frontend && npm run build`
  - 怎么回滚：`git revert <step4_sha>`
  - 删什么：前端 replay 对具体因子名的硬编码拼装分支
- [x] 步骤 5：全链路门禁与证据收集
  - 改什么：补 E2E 回归测试与 `docs/core/factor-modular-architecture.md` 同步
  - 怎么验收：`pytest -q`；`bash scripts/quality_gate.sh && bash scripts/e2e_acceptance.sh`
  - 怎么回滚：`git revert <step5_sha>`
  - 删什么：遗留临时调试开关/兼容路径

## 设计原则 / 红旗快检

- 本次采用的 P-Card
  - `P4` 深模块：把接入复杂度下沉到 capability manifest + compiler 层。
  - `P6` 接口简于实现：调用方维持稳定入口，不暴露装配细节。
  - `P10` 定义错误不存在：用拓扑校验与强一致门禁封堵错误路径。
  - `P11` 设计两次：保留 A/B 方案并给出取舍。
  - `P14` 增量以抽象为单位：先交付 capability/feature 抽象，再接入下游。
- 本次排查的 R-Card
  - `R1` 浅模块：避免“只有转发无价值”的 feature 层。
  - `R2` 信息泄漏：消除中心注册与前端因子名散点硬编码。
  - `R3` 时间分解：按领域编译器拆分，不按流程脚本堆叠。
  - `R6` 重复实现：统一 replay/backtest 的编译契约。
  - `R7` 通用/专用混杂：通用能力放 manifest，专用算法留在插件内。
  - `R11` 命名模糊：新增模块命名直接体现职责（feature/package compiler）。
  - `R13` 非显而易见：复杂分支必须收敛到小接口与可测组件。

## 风险与回滚

- 风险
  - 高风险跨边界改动（6+ 目录），若分层不清晰易引入连锁回归。
  - feature 强一致门禁可能暴露更多“历史隐性不同步”问题。
- 缓解
  - 分 5 个原子步骤实施，每步独立可回滚。
  - 每步执行对应最小验收，不通过不进入下一步。
- 回滚
  - 首选：`git revert <step_sha>`
  - 兜底：关闭 `TRADE_CANVAS_ENABLE_FEATURE_INGEST`（若新增开关），恢复旧读路径。

## 验收标准

- `pytest -q` 全量通过
- `cd frontend && npm install && npm run build` 通过
- `bash scripts/quality_gate.sh` 通过（禁兼容层/禁双轨）
- `bash scripts/e2e_acceptance.sh` 通过
- 新增因子接入演练：只改 `processor + bundle + capability` 即可被 factor/overlay/feature/replay/backtest/freqtrade 识别

## E2E 用户故事（门禁）

### Story ID / E2E Test Case（必须）
- Story ID：`2026-02-15/factor-capability/new-factor-one-line-enable`
- 关联 Plan：`docs/plan/2026-02-15-factor-one-shot.md`
- E2E 测试用例：
  - Test file path: `backend/tests/test_e2e_user_story_factor_capability_pipeline.py`（本计划新增）
  - Test name(s): `test_new_factor_can_enable_overlay_feature_freqtrade_without_core_patch`
  - Runner：`pytest`

### Persona / Goal
- Persona：量化策略研发工程师
- Goal：新增一个因子后，不修改 orchestrator/中心注册，即可按能力清单接入绘图、特征、回测和实盘。

### Entry / Exit（明确入口与出口）
- Entry：写入一段固定闭合 K 线，启用新因子 capability（overlay+feature+freqtrade）。
- Exit：
  - factor ledger 出现新因子事件；
  - overlay ledger 出现对应绘图指令；
  - feature ledger 出现对应列；
  - freqtrade annotate 输出对应 `tc_*` 列；
  - replay window 可读取对应增量。

### Concrete Scenario（必须：写具体数值）
- Chart / Symbol:
  - series_id / pair / timeframe: `binance:futures:BTC/USDT:1m`
  - timezone: UTC
- Initial State：
  - DB empty: yes
  - base=`1700200000`, step=60，共 12 根
  - closes=`[10,11,13,12,11,12,14,13,12,13,15,14]`
- Trigger Event：
  - finalized candle 到达 `1700200660` 与 `1700200720`
- Expected observable outcome：
  - `/api/factor/slices` 返回新因子 snapshot，且 `candle_id=binance:futures:BTC/USDT:1m:1700200720`
  - `/api/draw/delta` 的 `active_ids` 包含新因子绘图 id
  - freqtrade annotate 结果中新增列（例如 `tc_newfactor_score`）至少 1 行非空

### Preconditions（前置条件）
- 数据前置：测试内临时 sqlite
- 依赖服务：纯后端 pytest；前端通过 build 校验契约类型

### Main Flow（主流程步骤 + 断言）
1) Step: 写入 candles 并执行 ingest pipeline
   - User action: 触发 `IngestPipeline.run_sync`
   - Backend chain: candle -> factor -> overlay -> feature
   - Assertions: 各 ledger `head_time` 同步到 `1700200720`
   - Evidence: sqlite 查询输出 + pytest 断言
2) Step: 读取 world/replay
   - User action: 调用 world/read + replay window
   - Backend chain: read_models -> strict check -> response
   - Assertions: `candle_id` 与 `to_candle_id` 完全一致
   - Evidence: 响应 JSON 片段
3) Step: 运行 freqtrade annotate
   - User action: 调用 `annotate_factor_ledger`
   - Backend chain: feature read -> signal apply
   - Assertions: 新因子列存在且满足最小非空/非零阈值
   - Evidence: dataframe 列统计输出

### Produced Data（产生的数据）
- Tables / Files:
  - `factor_events` / `factor_head_snapshots`
  - `overlay_instruction_defs` / `overlay_instruction_versions`
  - `feature_*`（本轮新增）
  - replay package json（若启用 package 构建）

### Verification Commands（必须可复制运行）
- `pytest -q backend/tests/test_e2e_user_story_factor_capability_pipeline.py`
  - Expected：新增因子 capability 一次接入成功，且强一致门禁通过
- `pytest -q`
  - Expected：全量回归通过
- `cd frontend && npm install && npm run build`
  - Expected：类型与构建通过
- `bash scripts/quality_gate.sh && bash scripts/e2e_acceptance.sh`
  - Expected：质量门禁与 E2E 门禁通过

### Rollback（回滚）
- 最短回滚方式：按步骤提交逐个 `git revert <sha>`
- 灰度回退：关闭 `TRADE_CANVAS_ENABLE_FEATURE_INGEST`

## 变更记录
- 2026-02-15: 创建（草稿）
- 2026-02-15: 补齐 one-shot 架构方案、能力清单策略与 E2E 门禁草案
- 2026-02-15: 完成 M1~M5，P0~P2 旧链路清理与稳定性修复，并通过 quality gate + e2e acceptance
