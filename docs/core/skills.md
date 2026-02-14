# 项目 Skills（Codex）

本项目的 Codex skills 用于固化协作流程与约束。

## Skills 清单（按“真源位置”划分）

> 目的：避免“文档里写了一个 skill，但仓库里找不到 SKILL.md”导致流程漂移。

### 1) 本仓可用 skills（真源：`.codex/skills/`）

这些 skills 随仓库一起走（对其它机器最可复现）：

- `验收`：一句话收尾当前 worktree（review + merge main + 删除 worktree）；全生命周期管理请用 `tc-worktree-lifecycle`
- `tc-acceptance-e2e`：最终验收（宣称 done/已上线 前必须跑通 `scripts/e2e_acceptance.sh` 并交付证据）
- `tc-agent-browser`：浏览器自动化（`agent-browser`；用于截图/流程复现/证据）
- `tc-debug`：调试流程（可复现→定位→根因→最小修复→回归保护；优先“定义错误不存在”）
- `tc-e2e-gate`：开发过程 E2E 用户故事门禁（plan→开发→验证链路）；最终上线证据请配合 `tc-acceptance-e2e`
- `tc-fupan`：复盘（每次必输出 3 个主题；必要时同步 `docs/core/`）
- `tc-knowledge-storytelling`：知识写作（用白话叙事拆解硬核系统知识，保留逻辑链与术语锚点）
- `tc-learning-loop`：交付后学习闭环（提炼原子经验卡 + 置信度，稳定后升级为 skill）
- `tc-market-kline-fastpath-v2`：市场 K 线 Fastpath v2（保持 HTTP/WS 契约稳定，可回滚可验收）
- `tc-planning`：任务拆解与计划（每步可验收/可回滚；强制 A/B 方案取舍、新增文件理由卡、复杂度预算卡；大改动落盘 `docs/plan/`）
- `tc-context-compact`：上下文治理（战略 compact、切会话前快照、恢复契约）
- `tc-subagent-orchestration`：子 session 编排（fan-out 执行、回调日志、统一汇总报告）
- `tc-skill-authoring`：本项目 skill 编写指南（新增/修改 skills，并与文档索引、`doc-status` 约定联动）
- `tc-verify`：统一质量门禁（禁兼容层/禁遗留双轨/禁临时债）；`Doc Impact/交付三问` 以 `AGENTS.md` DoD 为真源
- `tc-worktree-lifecycle`：Worktree 生命周期管理（创建→开发→验收→删除）；分支命名统一 `codex/<topic>`

### 1.1 冲突裁决顺序（推荐）

当一次任务同时命中多个 skills，默认按下列顺序串联：

`tc-planning` → `tc-e2e-gate` → `tc-verify` → `tc-acceptance-e2e` → `验收`

边界提示：
- `tc-e2e-gate` 负责开发过程门禁；
- `tc-acceptance-e2e` 负责最终交付证据；
- `验收` 负责 worktree 收尾（其底层脚本可由 `tc-worktree-lifecycle` 调用）。
- 需要并行拆分子任务时，可在 `tc-planning` 后插入 `tc-subagent-orchestration`。

### 2) 全局 skills（真源：`$CODEX_HOME/skills/`，可能因机器而异）

这些通常由开发者自行安装/维护（不一定随仓库自动存在）：

- `systematic-debugging`：系统化调试（假设驱动 → 证据链 → 最小实验 → 根因定位）
- `playwright`：终端驱动 Playwright 浏览器自动化
- `frontend-design` / `ui-ux-pro-max` / `lightweight-charts`：前端/图表相关能力
- `skill-installer` / `skill-creator`：skills 安装与创建

#### 2.1 团队推荐第三方 skills（建议安装 + 按场景触发）

> 原则：这些 skills 属于全局能力，不纳入项目内 `.codex/skills/` 真源；在 `AGENTS.md` 中只写触发场景，详细说明放在本节，避免重复维护。

- `find-skills`（来源：`vercel-labs/skills`）
  - 用途：当用户询问“有没有 skill 能做 X / 如何扩展能力 / 帮我找 skill”时，先用它做发现与安装建议。
  - 触发建议：能力发现类问题默认触发。
- `supabase-postgres-best-practices`（来源：`supabase/agent-skills`）
  - 用途：后端涉及 Postgres/Supabase 的 SQL、索引、Schema、RLS、性能优化时，作为首选规则集。
  - 触发建议：只在数据库相关任务触发，避免泛化到非 DB 任务。
- `brainstorming`（来源：`obra/superpowers`）
  - 用途：产品方向、需求澄清、方案取舍阶段的结构化发散与收敛。
  - 触发建议：仅用于规划/创意探索；不替代本仓“三阶段工作流”和门禁要求。

## 真源位置

- 项目内 skills 真源：`./.codex/skills/`
- 文档索引真源：本文件（`docs/core/skills.md`）

## 安装（让 Codex 可发现项目 skills）

Codex 默认从 `$CODEX_HOME/skills/` 加载。推荐用软链接安装（不影响登录凭据）：

```bash
bash scripts/install_project_skills.sh
```

卸载：

```bash
bash scripts/install_project_skills.sh --uninstall
```
