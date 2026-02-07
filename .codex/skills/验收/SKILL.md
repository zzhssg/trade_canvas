---
name: 验收
description: "一句话验收当前 worktree：review gate →（可选）merge main → 删除 worktree（纯 git，不依赖 dev panel）。"
metadata:
  short-description: 一句话验收（纯 git 合并+删 worktree）
---

# 验收（纯 git 一句话验收）

目的：当你对 Codex 说“验收”时，把当前 worktree 的收尾动作变成可重复、可回滚、可追踪的一条命令。

本 skill **只做 worktree 生命周期的收尾**（review + merge + remove）。  
如果你要做“最终交付门禁”（Playwright E2E + 证据），请用 `tc-acceptance-e2e`。

---

## 1) 使用方式

在 feature worktree 的仓库根目录执行：

```bash
# 1) 默认动作（推荐）：先做 review + 门禁预检查（dry-run，不会合并/删除）
bash scripts/worktree_acceptance.sh

# 2) 真执行（推荐）：推进 plan 状态（已上线）+ doc_audit + merge 到 main + 删除 worktree + 删除本地分支，并 push main
bash scripts/worktree_acceptance.sh --yes --push --auto-doc-status --run-doc-audit

# 3) 合并后同时删除远端分支（可选）
bash scripts/worktree_acceptance.sh --yes --push --delete-remote --auto-doc-status --run-doc-audit
```

如果本次是中/高风险变更但 worktree metadata 没有填 `plan_path`，可显式指定：

```bash
bash scripts/worktree_acceptance.sh --yes --push --auto-doc-status --run-doc-audit --plan-doc docs/plan/2026-02-xx-my-feature.md
```

---

## 2) 门禁说明（脚本内置）

- 禁止在 `main` worktree 中执行
- feature worktree 必须 clean（无未提交改动）
- main worktree 也必须 clean
- `git diff --check main...<branch>` 必须为 clean（否则直接失败）
- **计划门禁（中/高风险强制）**：若本次变更不属于低风险（仅 docs/test/style），必须存在 `docs/plan/...` 且其状态为 `已上线/online`（并要求 `updated=今天`）
