---
title: 文档状态（status）约定
status: done
created: 2026-02-02
updated: 2026-02-05
---

# 文档状态（status）约定

本仓库部分 Markdown 使用 YAML front matter（文件开头的 `--- ... ---`）携带元数据，其中 `status` 用于标记“文档成熟度/与代码一致性预期”。

注意：截至 2026-02-02，仓库没有任何构建流程会自动读取/更新 `status`；它是**手工维护字段**。如果不制定流程与校验，文档会长期停留在 `draft/草稿`。

补充：本仓已在“验收门禁脚本”中加入了可选的 plan 状态校验（见 §4.3），用于把“开发完成”与“计划文档状态更新”绑定到同一条可执行门禁上。

## 1) 适用范围

建议凡是满足以下任一条件的文档都使用 front matter 并维护 `status`：
- `docs/core/`：核心 SoT / 架构 / 核心链路说明
- `docs/core/contracts/`：协议/数据结构契约（尤其是 v1/v2 版本化契约）
- `docs/runbook/`：运行手册（可操作、可复现）
- `docs/plan/`：计划文档（已约定 `草稿/开发中/已完成`）

## 2) 推荐状态枚举（允许中英双写）

为降低混用成本，审计脚本允许以下等价写法：

- `draft` / `草稿`：还在收敛中；可能不完整；实现可能尚未开始或仍频繁变化
- `in_progress` / `开发中`：已经进入实施；文档会跟着代码快速迭代
- `done` / `已完成`：核心内容已落地并通过验收；后续变更必须同步更新 `updated`
- `online` / `已上线`：**与 `done/已完成` 等价**；用于强调“已进入可交付状态/可宣称完成”（兼容历史文档与门禁口径）
- `deprecated` / `已废弃`：不再推荐使用；保留用于历史回溯（必要时给出替代链接）

## 3) 维护规则（Definition of Done）

每次“完成一件事”时，顺手更新文档状态，避免永远停在草稿：

- 当进入实现（开始写代码/开始切任务）：
  - 把对应设计/契约文档从 `draft` 改为 `in_progress`（或 `开发中`）
  - 同步更新 `updated: YYYY-MM-DD`
- 当验收通过（E2E/接口稳定/手工验收达标）：
  - 把文档状态改为 `done`（或 `已完成`）
  - 在文档末尾（或“变更记录”章节）补一条记录说明这次验收的口径
- 当接口被替换或策略废弃：
  - 改为 `deprecated`（或 `已废弃`），并给出替代文档入口

## 4) 自动化：状态审计脚本

使用：在仓库根目录运行：

```bash
bash docs/scripts/doc_frontmatter_audit.sh
```

它会：
- 统计各 `status` 数量并列出文件
- 校验 `status` 是否落在允许枚举里
- 校验 `created/updated` 是否为 `YYYY-MM-DD`，且 `updated >= created`

### 4.1 一键更新 status

```bash
# 进入实施
bash docs/scripts/doc_set_status.sh in_progress docs/core/backtest.md

# 验收完成
bash docs/scripts/doc_set_status.sh done docs/core/backtest.md

# 可交付/已上线（与 done 等价）
bash docs/scripts/doc_set_status.sh 已上线 docs/core/backtest.md
```

### 4.2 统一文档审计入口（推荐）

```bash
bash docs/scripts/doc_audit.sh
```

它会先检查仓库是否存在“docs/ 外的 Markdown”（除 `README.md` 外），再执行 `doc_frontmatter_audit.sh`（若存在）。

### 4.3 门禁：E2E 通过后强制更新 plan status（推荐）

当你准备“宣称完成”时，建议用下面方式跑 E2E（同时校验 plan 状态已更新为 `done/已完成` 且 `updated=今天`）：

```bash
E2E_PLAN_DOC="docs/plan/2026-02-02-single-factor-pipeline-v0.md" bash scripts/e2e_acceptance.sh
```

这样能避免“代码跑通了，但计划文档一直停留在草稿/开发中”的问题。
