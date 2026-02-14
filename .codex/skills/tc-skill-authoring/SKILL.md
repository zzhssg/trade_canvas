---
name: tc-skill-authoring
description: Guide for writing and maintaining project-local Codex skills for trade_canvas in .codex/skills, and keeping docs indexes in sync.
metadata:
  short-description: 本项目 skill 编写指南
---

# tc-skill-authoring（本项目 skill 编写指南）

当用户要求“为 trade_canvas 新增/修改 skill、整理项目内 skills、让 skill 与 docs 规范联动、补 skill 清单/索引、加脚本自动化”时，使用本技能。

## 本项目 skill 的真源位置

- **项目内 skills 真源**：`./.codex/skills/<skill-name>/SKILL.md`
- **文档索引真源**：`docs/core/skills.md`（列出有哪些 skills、用途、安装方式）

> 注意：Codex 默认只会从 `$CODEX_HOME/skills/` 加载 skills。项目内 `.codex/skills/` 需要“安装/链接”到 `$CODEX_HOME/skills/` 才能在 Codex 中触发。

## 目录规范（固定）

每个 skill：

```
.codex/skills/<skill-name>/
  SKILL.md
  scripts/        (可选)
  references/     (可选)
  assets/         (可选)
```

## 写作规范（强约束）

- `SKILL.md` 必须包含 YAML frontmatter：`name`、`description`（description 只写“何时使用”，不要塞流程细节）。
- 正文要短：只放流程与约束；大段参考资料放到 `references/`（需要时再读）。
- 技能名建议 **项目命名空间**：`tc-...`，避免与全局 skills 冲突。

## 与 docs 的联动（必须）

新增/修改 skill 时，同时做：

1) 更新 `docs/core/skills.md`（新增条目/用途/脚本）
2) 更新 `docs/core/README.md`（如果新增核心入口文档）
3) 跑 `bash docs/scripts/doc_audit.sh`
4) 如涉及状态字段，遵循 `docs/core/doc-status.md` 约定（`status` + `updated` 同步维护）

## 安装（让 Codex 能发现项目 skills）

用本仓库脚本把项目内 skills 链接到默认 Codex home：

```bash
bash scripts/install_project_skills.sh
```

卸载：

```bash
bash scripts/install_project_skills.sh --uninstall
```
