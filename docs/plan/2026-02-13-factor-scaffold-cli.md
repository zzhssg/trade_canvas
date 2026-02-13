---
title: 新增因子脚手架命令（new_factor_scaffold）
status: 待验收
owner: Codex
created: 2026-02-13
updated: 2026-02-13
---

## 背景

当前因子插件化已经完成，但“新增因子”仍依赖人工复制 `processor` 与 `bundle` 文件，容易漏改（命名、依赖、bucket key 不一致）。
为了保持敏捷迭代与干净架构，需要把重复接入动作标准化为一个脚手架命令。

## 目标 / 非目标

### 目标
- 提供一个命令，自动生成新增因子最小骨架（processor + bundle）。
- 默认 fail-fast：非法命名、文件已存在直接失败，不做隐式兼容。
- 输出可直接进入现有自动发现链路（`factor/bundles`）。

### 非目标
- 本轮不自动修改算法逻辑、不改 runtime 行为。
- 本轮不自动更新所有文档/测试，只提供稳定骨架与说明。

## 方案概述（Design it Twice）

### A 方案（采用）：单脚本模板渲染
- 新增 `scripts/new_factor_scaffold.py`，接收 `--factor/--depends-on`，生成两个文件。
- 优点：实现轻、可直接在当前仓库使用、回滚成本低。
- 缺点：模板维护在脚本中，未来如要多模板需要扩展。

### B 方案：抽象成包内生成器 + 脚本薄封装
- 在 `backend/app/factor/` 增加生成器模块，脚本只做 CLI 包装。
- 优点：更易复用；缺点：引入运行时代码边界污染（工具能力进入业务包）。

取舍：选 A，保持工具与运行时代码解耦。

## 任务拆解

1) 新增脚手架脚本
- 改什么：`scripts/new_factor_scaffold.py`
- 验收：`pytest -q tests/test_factor_scaffold_cli.py`
- 回滚：`git revert <sha>`
- 删什么：不新增兼容别名/旧脚手架双轨

2) 补回归测试
- 改什么：`tests/test_factor_scaffold_cli.py`
- 验收：`pytest -q tests/test_factor_scaffold_cli.py`
- 回滚：`git revert <sha>`
- 删什么：无

3) 文档补充
- 改什么：`docs/core/factor-modular-architecture.md`
- 验收：`bash docs/scripts/doc_audit.sh`
- 回滚：`git revert <sha>`
- 删什么：删除“仅靠手工复制新增因子”的描述

## 设计原则/红旗快检

### 采用的 P-Card
- `P2`：能跑不等于完成，必须有脚本 + 测试 + 文档。
- `P6`：接口简于实现，调用方只记一个命令。
- `P10`：通过命名校验/文件存在校验，定义错误不存在。
- `P11`：A/B 方案对比后落地。

### 排查的 R-Card
- `R2` 信息泄漏：避免每次新增因子在多处手工抄写。
- `R5` 透传方法：脚手架不做无意义转发，直接生成可用骨架。
- `R6` 重复实现：统一模板减少复制粘贴。
- `R11` 命名模糊：强约束 factor_name 正则。
- `R13` 非显而易见代码：输出文件结构与字段固定、可预测。

## 风险与回滚

- 风险：模板字段与当前契约漂移。
- 缓解：测试断言关键片段，文档注明生成后需补业务逻辑。
- 回滚：按提交回退脚本与测试，不影响运行时。

## 验收标准

- 命令可生成 `processor_<factor>.py` 与 `bundles/<factor>.py`。
- 非法命名/冲突文件可 fail-fast。
- 测试通过，文档审计通过。

## E2E 用户故事（门禁）

### Story ID / E2E Test Case（必须）
- Story ID：`2026-02-13/factor-scaffold/cli-generate-two-files`
- 关联 Plan：`docs/plan/2026-02-13-factor-scaffold-cli.md`
- E2E 测试用例：
  - Test file path: `tests/test_factor_scaffold_cli.py`
  - Test name(s):
    - `test_cli_generates_processor_and_bundle_files`
    - `test_cli_rejects_invalid_factor_name`
  - Runner：pytest

### Persona / Goal
- Persona：因子研发工程师
- Goal：用一条命令生成可接入的因子骨架，减少手工错误。

### Entry / Exit（明确入口与出口）
- Entry：执行 `python3 scripts/new_factor_scaffold.py --factor trend_break --depends-on pivot,pen`
- Exit：生成两个文件，且脚本退出码为 0。

### Concrete Scenario（必须：写具体数值）
- factor_name：`trend_break`
- depends_on：`pivot,pen`
- 预期输出：
  - `backend/app/factor/processor_trend_break.py`
  - `backend/app/factor/bundles/trend_break.py`

### Verification Commands（必须可复制运行）
- `pytest -q tests/test_factor_scaffold_cli.py`
- `pytest -q`
- `bash docs/scripts/doc_audit.sh`

## 变更记录
- 2026-02-13: 创建（草稿）
- 2026-02-13: 状态推进为开发中并完成实现
- 2026-02-13: 状态推进为待验收
