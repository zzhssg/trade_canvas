---
name: tc-worktree-lifecycle
description: "Enforce worktree lifecycle gates: creation requires description + plan link; acceptance requires E2E pass + review; deletion requires merge confirmation. Use when creating, developing, or completing work in a worktree."
metadata:
  short-description: Worktree 生命周期管理门禁
---

# tc-worktree-lifecycle（Worktree 生命周期管理）

目标：把 worktree 的"创建→开发→验收→删除"收敛到一个可追踪的生命周期，并在关键节点设置门禁。

本技能分四阶段强约束：

- **创建阶段**：必须提供功能介绍（description），建议链接 plan 文档
- **开发阶段**：遵循 tc-e2e-gate，保持元数据更新
- **验收阶段**：E2E 通过 + Code Review + Plan 状态更新
- **删除阶段**：确认已合并到 main，归档元数据

---

## 1) 创建阶段（Creation Gate）

### 1.1 硬约束

创建新 worktree 时必须满足：

- **必须提供 description**：至少 20 个字符，描述这个 worktree 的目的
- **plan 文档（中/高风险必填）**：`docs/plan/YYYY-MM-DD-<topic>.md`
  - 低风险（仅 docs/test/style）允许不建 plan
  - 中/高风险（任何非低风险改动）必须有 plan（否则 `scripts/worktree_acceptance.sh` 会在验收门禁失败）
- **分支命名规范**：`{type}/{feature-name}`，如 `feature/draw-tools-v1`

### 1.2 创建方式

通过开发者面板创建：

1. 访问 `/dev` 页面
2. 点击 "New Worktree"
3. 填写分支名、功能介绍、plan 路径
4. 系统自动分配端口并创建 worktree

或通过 API 创建：

```bash
curl -X POST http://localhost:8000/api/dev/worktrees \
  -H "Content-Type: application/json" \
  -d '{
    "branch": "feature/my-feature",
    "description": "实现 XXX 功能，包括 A、B、C 三个模块",
    "plan_path": "docs/plan/2026-02-xx-my-feature.md",
    "base_branch": "main"
  }'
```

### 1.3 创建阶段的退出条件

- worktree 已创建
- 元数据已保存到 `.worktree-meta/{id}.json`
- 端口已分配

---

## 2) 开发阶段（Development Phase）

### 2.1 开发过程的约束

- 遵循 `tc-e2e-gate` 的 E2E 用户故事门禁
- 保持 worktree 元数据更新（如 plan 路径变更）
- 定期同步 main 分支避免冲突
- **状态联动（必须）**：
  - 开始开发时执行：`bash scripts/worktree_plan_ctl.sh status 开发中`
  - 开发完成准备提测时执行：`bash scripts/worktree_plan_ctl.sh status 待验收`

### 2.2 服务管理

通过开发者面板管理服务：

- **启动服务**：点击 "Start" 启动前后端
- **停止服务**：点击 "Stop" 停止服务
- **打开页面**：点击 "Open" 在浏览器中打开

端口分配策略：

```
Main worktree:     Backend 8000, Frontend 5173
Worktree #1:       Backend 8001, Frontend 5174
Worktree #2:       Backend 8002, Frontend 5175
...
```

---

## 3) 验收阶段（Acceptance Gate）

### 3.1 验收前必须完成

- [ ] E2E 用户故事通过（`tc-e2e-gate`）
- [ ] Code Review 完成
- [ ] Plan 状态已更新为“待验收”
- [ ] 无 P0 技术债

### 3.2 验收命令

```bash
bash scripts/worktree_acceptance.sh
```

验收脚本会：

1. 输出 review 信息（commit 列表 / diff stat / diff check）
2. 准备 main（checkout + 可选 ff-only 同步远端 main）
3. 执行 merge 到 main（需要 `--yes`）
4. 删除 worktree + 删除本地分支（需要 `--yes`）

默认是 dry-run，不会真正合并/删除；真正执行用：

```bash
# 在 feature worktree 内执行（推荐）
bash scripts/worktree_acceptance.sh --yes --push --auto-doc-status --run-doc-audit

# 如需合并后删除远端分支（可选）
bash scripts/worktree_acceptance.sh --yes --push --delete-remote --auto-doc-status --run-doc-audit
```

如果 metadata 里没有 plan_path，可显式指定：

```bash
bash scripts/worktree_acceptance.sh --yes --push --auto-doc-status --run-doc-audit --plan-doc docs/plan/2026-02-xx-my-feature.md
```

### 3.3 验收阶段的退出条件

- 所有门禁检查通过
- 分支已合并到 main
- worktree 已删除
- 元数据已归档

---

## 4) 删除阶段（Deletion Gate）

### 4.1 删除前必须确认

- [ ] 分支已合并到 main
- [ ] 服务已停止
- [ ] 无未提交的更改

### 4.2 删除方式

通过开发者面板删除：

1. 确保服务已停止
2. 点击 "Delete" 按钮
3. 确认删除

或通过 API 删除：

```bash
curl -X DELETE http://localhost:8000/api/dev/worktrees/{worktree_id} \
  -H "Content-Type: application/json" \
  -d '{"force": false}'
```

或纯 git 删除（不依赖 dev panel）：

```bash
# 在任意 worktree 执行；建议在 main worktree 内执行
git worktree remove /path/to/worktree
```

### 4.3 删除后

- 元数据归档到 `.worktree-meta/archive/`
- 端口分配释放
- worktree 目录删除

---

## 5) 常见反例（直接判定"不通过"）

- 创建 worktree 时没有提供 description
- 验收时 E2E 未通过就宣称完成
- 删除 worktree 时分支未合并到 main
- 服务运行时强制删除 worktree

---

## 6) 相关资源

- 开发者面板：`/dev` 页面
- 元数据目录：`.worktree-meta/`
- 验收脚本：`scripts/worktree_acceptance.sh`
- E2E 门禁：`tc-e2e-gate` skill
