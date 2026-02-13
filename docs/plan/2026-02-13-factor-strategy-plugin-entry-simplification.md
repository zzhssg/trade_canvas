---
title: 因子与策略插件入口瘦身（自动发现 + 单点契约）
status: 待验收
owner: Codex
created: 2026-02-13
updated: 2026-02-13
---

## 背景

当前新增一个因子通常要同时改 `backend/app/factor/default_components.py`（注册）与 `backend/app/factor/slice_plugins.py`（读插件实现）。
新增策略信号也需要改 `backend/app/freqtrade/signal_plugins.py` 的默认列表。
这种“中心文件持续膨胀”的模式会形成治理债，和“快速迭代 + 干净架构”目标冲突。

## 目标 / 非目标

### 目标
- 新增因子时，不再修改中心注册文件（默认组件由目录自动发现）。
- 新增策略信号时，不再修改中心注册文件（默认策略插件由目录自动发现）。
- 保持现有对外契约不变（factor catalog / factor slices / freqtrade annotate）。
- 保持 fail-fast（缺配对、依赖环、重名时启动即报错）。

### 非目标
- 本轮不引入兼容双轨（不保留旧注册入口）。
- 本轮不改算法行为（pivot/pen/zhongshu/anchor 语义不变）。
- 本轮不新增 HTTP/WS API。

## 方案概述

### 方案 A（保守）
- 继续中心显式注册，只把大文件拆小。
- 优点：变更小。
- 缺点：新增因子/策略仍要改中心文件，R2 信息泄漏持续。

### 方案 B（采用）
- 新增 `factor/bundles/`：每个因子 bundle 文件同时定义 slice plugin，并提供 `build_bundle()`；
  `default_components` 扫描目录自动发现并按依赖拓扑排序。
- 新增 `freqtrade/signal_strategies/`：策略插件按目录自动发现并按依赖拓扑排序。
- 优点：新增点本地化、回滚简单、中心文件不再增长。
- 取舍：引入发现逻辑复杂度，但通过 fail-fast + 测试覆盖控制风险。

取舍依据：
- 契约稳定性：B 不改外部契约，仅改装配方式。
- 回滚成本：B 可按提交 `git revert`，且不涉及数据迁移。
- 验收成本：B 可用现有 factor/freqtrade 回归测试覆盖主链路。

## 变更影响评估

- 预计触及 6+ 文件，属于架构预警改动；按“先降耦合、后扩展”执行。
- 边界：仅改 `backend/app/factor/` 与 `backend/app/freqtrade/`，不改 route/schema。
- 回滚：整组提交可单独 revert，恢复静态注册。

## 新文件理由卡

- `backend/app/factor/bundles/`：因子级装配边界，避免中心注册文件承担所有因子信息。
- `backend/app/freqtrade/signal_strategies/`：策略插件装配边界，避免 signal_plugins 单文件膨胀。
- 所有新增生产文件保持 >=50 行；`__init__.py` 仅做导出/装配（骨架例外）。

## 任务拆解

1) 建立因子 bundle 自动发现
- 改什么：
  - 新增 `backend/app/factor/bundles/*.py`（pivot/pen/zhongshu/anchor）
  - 修改 `backend/app/factor/default_components.py`
  - 精简 `backend/app/factor/slice_plugins.py` 为导出层
- 怎么验收：
  - `pytest -q backend/tests/test_factor_default_components.py backend/tests/test_factor_manifest.py backend/tests/test_factor_slice_plugins.py`
- 怎么回滚：
  - 回退本提交即可恢复静态注册。
- 删什么：
  - 删除旧的中心硬编码注册列表（不保留双轨）。

2) 建立策略 signal 自动发现
- 改什么：
  - 新增 `backend/app/freqtrade/signal_strategies/pen_direction.py`
  - 新增 `backend/app/freqtrade/signal_strategies/__init__.py`
  - 修改 `backend/app/freqtrade/signal_plugins.py`
- 怎么验收：
  - `pytest -q backend/tests/test_freqtrade_adapter_v1.py`
- 怎么回滚：
  - 回退本提交即可恢复旧默认列表。
- 删什么：
  - 删除 `signal_plugins.py` 中硬编码默认插件列表。

3) 文档与总回归
- 改什么：
  - 更新 `docs/core/factor-modular-architecture.md`
  - 更新 `docs/core/contracts/factor_plugin_v1.md`
- 怎么验收：
  - `pytest -q`
  - `bash docs/scripts/doc_audit.sh`
- 怎么回滚：
  - 回退文档提交（不影响运行）。
- 删什么：
  - 删除文档中“必须改中心文件注册”的旧描述。

## 设计原则 / 红旗快检

### 本次采用的 P-Card
- `P4` 深模块：把“注册复杂度”下沉到 bundle/signal_strategies 层。
- `P6` 接口简于实现：调用方仍用 `build_default_*`，不感知发现细节。
- `P9` 复杂度下沉：把依赖排序/冲突校验集中到发现器。
- `P11` 设计两次：已比较 A/B 并记录取舍。
- `P14` 增量以抽象为单位：先交付插件装配抽象，再叠加新因子/新策略。

### 本次排查的 R-Card
- `R1` 浅模块：通过发现器 + fail-fast 避免只做透传。
- `R2` 信息泄漏：去掉中心硬编码列表，收敛为目录内声明。
- `R3` 时间分解：按领域（factor/strategy）而非执行步骤拆分模块。
- `R6` 重复实现：统一发现/拓扑校验流程，避免多处重复注册逻辑。
- `R7` 通用/专用混杂：通用装配在 `__init__`，专用算法留在各插件文件。
- `R11` 命名模糊：采用 `*_bundle` / `signal_strategies` 明确职责。
- `R13` 非显而易见代码：发现失败全部给出明确错误码。

## 验收标准

- 新增因子默认接入不需要改中心注册文件。
- 新增策略信号默认接入不需要改中心注册文件。
- 现有 factor/freqtrade 核心测试全部通过。
- 文档审计通过。

## E2E 用户故事（门禁）

### Story ID / E2E Test Case（必须）
- Story ID：`2026-02-13/plugin-entry/factor-and-signal-autodiscovery`
- 关联 Plan：`docs/plan/2026-02-13-factor-strategy-plugin-entry-simplification.md`
- E2E 测试用例：
  - Test file path: `backend/tests/test_factor_default_components.py`
  - Test name(s): `test_default_components_keep_tick_plugin_and_slice_plugin_order_aligned`
  - Runner：pytest

### Persona / Goal
- Persona：因子/策略研发工程师
- Goal：新增插件时只在插件目录落文件，不再改中心注册文件

### Entry / Exit（明确入口与出口）
- Entry：系统启动时装配默认 factor 与 signal 插件
- Exit：`build_default_factor_components()` 与 `build_default_freqtrade_signal_plugins()` 返回拓扑稳定顺序，freqtrade annotate 主链路可跑通

### Concrete Scenario（必须：写具体数值，禁止空泛）
- series_id / timeframe：`binance:futures:BTC/USDT:1m`
- 输入价格序列（freqtrade adapter 用例）：`[1,2,5,2,1,2,5,2,1,2,5,2,1]`
- 预期可观测结果：
  - factor 默认顺序：`pivot -> pen -> zhongshu -> anchor`
  - `annotate_factor_ledger()` 输出中 `tc_pen_confirmed.sum() >= 1`

### Preconditions（前置条件）
- 使用测试临时 DB（`backend/tests/test_freqtrade_adapter_v1.py` 现有 setup）
- 环境变量由测试用例内部设置

### Main Flow（主流程步骤 + 断言）
1) 默认因子装配
- User action：运行 factor 默认组件测试
- Requests：无（本地函数调用）
- Backend chain：`build_default_factor_components -> bundle discovery -> graph topo`
- Assertions：tick/slice 顺序一致且等于 `pivot, pen, zhongshu, anchor`
- Evidence：pytest 通过输出

2) 因子切片拓扑执行
- User action：运行 factor slice service 测试
- Requests：无
- Backend chain：`FactorSlicesService -> graph topo -> plugin build_snapshot`
- Assertions：调用顺序为 `alpha,beta,gamma`（拓扑顺序）
- Evidence：`backend/tests/test_factor_slice_plugins.py` 通过

3) 策略信号主链路
- User action：运行 freqtrade adapter 测试
- Requests：无
- Backend chain：`annotate_factor_ledger -> signal discovery -> signal apply`
- Assertions：`res.ok=True` 且 `tc_pen_confirmed.sum() >= 1`
- Evidence：`backend/tests/test_freqtrade_adapter_v1.py` 通过

### Produced Data（产生的数据）
- SQLite（测试临时库）
  - 关键表：factor history/head（由 orchestrator 写入）
  - 关键字段：`factor_name`, `kind`, `candle_time`, `event_key`
- DataFrame（freqtrade 测试输出）
  - 关键字段：`tc_pen_confirmed`, `tc_pen_dir`, `tc_enter_long`, `tc_enter_short`

### Verification Commands（必须可复制运行）
- `pytest -q backend/tests/test_factor_default_components.py backend/tests/test_factor_manifest.py backend/tests/test_factor_slice_plugins.py backend/tests/test_freqtrade_adapter_v1.py`
  - Expected：4 个测试文件全部通过；默认顺序与主链路断言成立。
- `pytest -q`
  - Expected：全量回归通过（退出码 0）。

### Rollback（回滚）
- `git revert <commit_sha>` 回退本次装配重构提交。

## 风险与回滚

- 风险：自动发现漏扫或误扫模块导致启动失败。
- 缓解：
  - 仅扫描约定目录/命名；
  - 每个模块 fail-fast 报错含模块名；
  - 测试覆盖默认装配 + 主链路。
- 回滚：按提交回退，恢复原静态注册实现。

## 变更记录
- 2026-02-13: 创建（草稿）
