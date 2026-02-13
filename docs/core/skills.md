# 项目 Skills（Codex）

本项目的 Codex skills 用于固化协作流程与约束。

## Skills 清单（按“真源位置”划分）

> 目的：避免“文档里写了一个 skill，但仓库里找不到 SKILL.md”导致流程漂移。

### 1) 本仓可用 skills（真源：`.codex/skills/`）

这些 skills 随仓库一起走（对其它机器最可复现）：

- `验收`：一句话验收 worktree（纯 git review + merge main + 删除 worktree；不依赖 dev panel）
- `tc-acceptance-e2e`：最终验收（宣称 done/已上线 前必须跑通 `scripts/e2e_acceptance.sh` 并交付证据）
- `tc-agent-browser`：浏览器自动化（`agent-browser`；用于截图/流程复现/证据）
- `tc-debug`：调试流程（可复现→定位→根因→最小修复→回归保护；优先“定义错误不存在”）
- `tc-e2e-gate`：E2E 用户故事门禁（规划阶段必须给完整 E2E 用户故事；开发结束必须验证通过并给证据；强制 Post-Dev Review 与“交付三问”；API 变更必须同步维护 `docs/core/api/v1/` 并通过 `doc_audit`）
- `tc-fupan`：复盘（每次必输出 3 个主题；必要时同步 `docs/core/`）
- `tc-knowledge-storytelling`：知识写作（用白话叙事拆解硬核系统知识，保留逻辑链与术语锚点）
- `tc-market-kline-fastpath-v2`：市场 K 线 Fastpath v2（保持 HTTP/WS 契约稳定，可回滚可验收）
- `tc-planning`：任务拆解与计划（每步可验收/可回滚；强制 A/B 方案取舍、新增文件理由卡、复杂度预算卡；大改动落盘 `docs/plan/`）
- `tc-skill-authoring`：本项目 skill 编写指南（新增/修改 skills，并与文档索引联动）
- `tc-verify`：统一质量门禁（禁兼容层/禁遗留双轨/禁临时债，交付前强制跑 `bash scripts/quality_gate.sh`）
- `tc-worktree-lifecycle`：Worktree 生命周期管理（创建→开发→验收→删除门禁，配合 `/dev` 与 `.worktree-meta/`）

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

### 3) 文档中提到但当前未落盘（planned / 待补）

以下条目若在协作中需要用到，建议尽快补齐到 `.codex/skills/` 或从全局 skills 引入：

- `tc-docs`

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
