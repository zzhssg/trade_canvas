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
