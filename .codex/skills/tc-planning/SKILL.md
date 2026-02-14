---
name: tc-planning
description: Use when work spans multiple steps/files or needs phased delivery; creates a small, verifiable plan and (if large) a docs/plan entry.
metadata:
  short-description: 任务拆解与计划（可验收/可回滚）
---

# tc-planning（任务拆解与计划）

目标：把工作拆成可验证的小步，并确保“每一步都有验收点”。

## 什么时候必须做计划

- 涉及 ≥2 个模块/目录
- 需要分阶段交付（MVP→迭代）
- 有明确回滚/风险控制需求
- 需要写/改 `docs/core/` 契约或 `docs/plan/` 计划

## 计划格式（必须）

每一步都写清三件事：

- **改什么**：文件/模块/接口（带路径）
- **怎么验收**：命令/测试/可观测结果
- **怎么回滚**：撤销改动的最短方式
- **删什么**：本轮必须移除的旧文件/旧函数/旧接口（禁止“新旧双轨并存”）

## 新增因子起手命令（新增约束）

当计划包含“新增 factor 插件”时，先用脚手架生成骨架，再写 A/B 方案取舍，避免手写入口遗漏：

```bash
python3 scripts/new_factor_scaffold.py --factor <name> --depends-on <dep1,dep2> --dry-run
python3 scripts/new_factor_scaffold.py --factor <name> --depends-on <dep1,dep2>
```

- 先 `--dry-run` 校验命名、依赖与目标路径，再落盘。
- 生成后必须在 plan 写清：替代哪个旧实现、会删除哪些遗留路径、验收命令与回滚命令。

## 架构质量补充（必须）

- **两次设计（Design it Twice）**：每个行为变更至少给出 A/B 两种方案，并写明最终取舍理由（契约稳定性、回滚成本、验收成本）。
- **新增文件理由卡**：按 `AGENTS.md`《结构复杂度硬约束 / 2) 新文件规则》说明领域归属、替代关系与扩展边界。
- **变更影响分级卡**：按 `AGENTS.md`《结构复杂度硬约束 / 5) 变更影响评估》先判定影响面，再决定是否先降耦合。
- **复杂度与接口卡**：按 `AGENTS.md`《结构复杂度硬约束 / 1) 文件大小门禁`、`3) 接口约束`、`6) 前端拆分约束》逐项检查并记录超限处理。
- **通用性边界**：默认做“适度通用”接口；若选择专用实现，必须写清适用范围与退场条件，防止一次性特化固化为长期负担。
- **依赖方向卡**：按 `AGENTS.md`《结构复杂度硬约束 / 4) 依赖方向规则》核对单向数据流，明确边界违规处理。

## 设计原则快检（P/R，必须）

- 方案里至少显式引用 3 个 `P*`（来自 `AGENTS.md` 的 `P-Card`），说明“本次如何落地”。
- 对以下红旗至少排查 5 项并给结论：`R1`/`R2`/`R3`/`R5`/`R6`/`R7`/`R8`/`R11`/`R13`。
- 若命中任一 `R*`，计划必须包含“修复步骤 + 验收命令 + 回滚路径”。
- 若难以命名（`R11`）或难以描述（`R12`），先重构抽象再继续加功能。

## 新文件反模式检查（必须）

- 检查是否出现 `Policy` / `Registry` / `Router` 包装单个纯函数或单个 dict 转发。
- 若命中小文件例外条款，必须在 plan 明确“为何例外 + 何时并回主模块”。

## 大改动落盘（按需）

- 大型方案/多里程碑：新建 `docs/plan/YYYY-MM-DD-主题-kebab-case.md`（用 `docs/plan/_template.md`）。
- 仅做小修小补：可以不写 plan 文档，但仍要有步骤+验收。

## 与项目面板联动（必须）

只要本次任务需要计划文档（尤其是中/高风险），必须在落盘后立刻完成 worktree 绑定与状态推进：

1. 生成 plan（新建或复用）：

```bash
bash docs/scripts/new_plan.sh "你的计划标题"
```

2. 绑定当前 worktree 与 plan（让项目面板可展示“计划文档”）：

```bash
bash scripts/worktree_plan_ctl.sh bind docs/plan/YYYY-MM-DD-xxx.md
```

3. 进入执行时，把 plan 状态置为“开发中”：

```bash
bash scripts/worktree_plan_ctl.sh status 开发中
```

4. 开发完成、准备交付时，把状态置为“待验收”：

```bash
bash scripts/worktree_plan_ctl.sh status 待验收
```
