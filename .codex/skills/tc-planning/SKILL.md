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

## 架构质量补充（必须）

- **两次设计（Design it Twice）**：每个行为变更至少给出 A/B 两种方案，并写明最终取舍理由（契约稳定性、回滚成本、验收成本）。
- **新增文件理由卡（硬约束）**：新增文件时必须写明“替代了哪个旧文件”或“为什么不能扩展现有文件”。
- **变更影响分级卡（硬约束）**：先估算本次功能改动涉及文件数（1-2 正常；3-5 必须解释；6+ 先做降耦合计划再进功能开发）。
- **复杂度预算卡（硬约束）**：Python 生产文件 `<=300` 行、TSX 组件 `<=400` 行（`>300` 先拆分）、React hook `<=150` 行。
- **通用性边界**：默认做“适度通用”接口；若选择专用实现，必须写清适用范围与退场条件，防止一次性特化固化为长期负担。
- **接口体量卡（硬约束）**：函数/构造器参数 `<=8`；dataclass/配置对象字段 `<=15`，超限必须按领域分组。
- **依赖方向卡（硬约束）**：方案里显式核对 `ingest -> store -> factor -> overlay -> read_model -> route` 单向链路，且 `route` 不直连 `store`。
- **前端状态卡（硬约束）**：组件直接 `useState` 不超过 5 个；`useEffect` 超过 3 个必须提取 hook；Zustand 单 slice 字段不超过 10 个。

## 新文件与小文件反模式（必须）

- 新增文件必须写明所属领域包（如 `ingest/`、`overlay/`）。
- 禁止新增少于 50 行的独立生产文件；若必须例外，需在 plan 记录收益、替代方案、回滚路径。
- 禁止用 `Policy` / `Registry` / `Router` 命名包装单个纯函数或单个 dict 转发。

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
