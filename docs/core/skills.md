# 项目 Skills（Codex）

本项目的 Codex skills 用于固化协作流程与约束。

## Skills 清单

- `tc-docs`：本项目文档规范（`docs/` / `docs/core/` / `docs/plan/` + plan 状态维护）
- `tc-skill-authoring`：本项目 skill 编写指南（新增/修改 skills，并与文档索引联动）
- `tc-planning`：任务拆解与计划（每步可验收/可回滚；大改动落盘 `docs/plan/`）
- `tc-market-kline-fastpath-v2`：市场 K 线 Fastpath v2（freqtrade 历史复用 + 批量落库 + 可插拔实时源；保持 HTTP/WS 契约与可回滚验收）
- `tc-fupan`：复盘（主题 1：一个主题内合并“错误复盘 + 经验沉淀”；主题 2：技术债/bug 审计；主题 3：技术债取舍（修债 vs 继续开发功能）给出明确建议；必要时同步 `docs/core/`；每次必输出 3 个主题）
- `tc-e2e-gate`：E2E 用户故事门禁（规划阶段必须给完整 E2E 用户故事；必须写“具体场景与具体数值”；开发结束必须验证通过并给证据；新增/变更 API 必须同步维护 `docs/core/api/v1/` 且通过 `doc_audit`）
- `tc-acceptance-e2e`：最终验收（宣称 done 前必须跑通 `scripts/e2e_acceptance.sh`，并交付 `output/playwright/` 证据；包含 E2E 漂移/隔离常见坑位清单）
- `验收`：一句话验收 worktree（纯 git review + merge main + 删除 worktree；不依赖 dev panel）
- `tc-agent-browser`：浏览器自动化（`agent-browser` 替代/补充 Playwright；`snapshot` + refs 更适合 LLM；用于快速跑流程、复现 UI、出截图/trace 证据）
- `tc-debug`：调试流程（可复现→定位→根因→最小修复→回归保护）
- `tc-worktree-lifecycle`：Worktree 生命周期管理（创建时必须有 description；验收时 review + merge；删除时归档元数据；配合开发者面板 `/dev` 使用）
- `systematic-debugging`（全局）：系统化调试（假设驱动 → 证据链 → 最小实验 → 根因定位；适合复杂问题/回归/性能与稳定性问题）
- `tc-verify`：交付验收门禁（任何“完成/修复”都要给验证命令+可观测结果）
- `trade-docs`（全局）：通用版文档规范（与本项目兼容；项目优先用 `tc-docs`）
- `using-superpowers`（全局）：通用“技能使用流程”说明（面向其它平台的 Skill tool 机制；在 Codex CLI 下不建议安装/启用，避免与本项目的 skills 触发规则产生冲突）

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
