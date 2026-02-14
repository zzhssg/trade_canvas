---
name: tc-e2e-gate
description: "Enforce an E2E user-story gate for trade_canvas work: during planning require a complete end-to-end user story covering the main flow; during development require passing that E2E story before declaring done; during delivery require reporting the story, flow, produced data, and concrete evidence (commands + outputs/artifacts). Use when planning/implementing any feature or fix that spans multiple components or changes behavior."
---

# tc-e2e-gate（开发过程 E2E 用户故事门禁）

目标：把“需求→实现→验证”绑定到一条可运行的 E2E 用户故事，避免只做局部功能却无法主链路验收。

与其他 skills 的边界：
- `tc-e2e-gate`：开发过程门禁（从 plan 到开发完成）。
- `tc-acceptance-e2e`：最终交付门禁（上线前证据）。
- `tc-verify`：结构与质量门禁（禁兼容层/禁双轨/禁临时债）。
- `验收` / `tc-worktree-lifecycle`：worktree 收尾与生命周期管理。

统一真源：
- DoD、`Doc Impact`、`交付三问`、文档状态推进以 `AGENTS.md` 与 `docs/core/agent-workflow.md` 为准。

---

## 1) 触发条件（命中即启用）

- 跨模块行为变更（FE+BE、pipeline+storage、adapter+contract）。
- 任何会改变主链路输入/输出语义的 `feat` / `fix` / `refactor`。
- 单模块改动但无现成回归保护、需要用 E2E 保证主流程时。

---

## 2) 规划阶段（先有故事，后写代码）

必须在 `docs/plan/YYYY-MM-DD-<topic>.md` 写出完整 E2E 用户故事（可复用 `assets/e2e_user_story_template.md`）：
- Persona + Goal（单一主角、单一目标）。
- 入口/出口（从哪个输入进入，到哪个可观测结果结束）。
- 主流程步骤与逐步断言（每一步可验证成功/失败）。
- 至少 1 个具体数值场景（禁止“预期成功”空话）。
- 证据采集命令与产物路径。

补充约束：
- 新增 factor：先跑 `python3 scripts/new_factor_scaffold.py --factor <name> --depends-on <dep1,dep2> --dry-run`。
- 新增/修改 HTTP/WS/SSE：先跑 `bash docs/scripts/api_docs_audit.sh --list`，并同步维护 `docs/core/api/v1/`。

---

## 3) 开发阶段（按故事推进）

- 每个子任务必须映射到 E2E 故事中的某一步断言。
- 故事失真时先改 plan，再改实现。
- 结束前至少完成：
  - 质量门禁：`bash scripts/quality_gate.sh`
  - 文档审计：`bash docs/scripts/doc_audit.sh`
  - E2E 验证：`bash scripts/e2e_acceptance.sh`（或本轮计划中定义的等价主链路命令）

---

## 4) 交付证据（最小集合）

交付说明至少给出：
- 本轮 E2E 用例路径（test file + test name）。
- 运行命令、退出码、关键输出。
- 产物路径（如 `output/playwright/`、日志、快照）。
- 关键数值结果（来源需可复核：UI/接口/SQL/日志）。

推荐顺序：
`tc-planning` → `tc-e2e-gate` → `tc-verify` → `tc-acceptance-e2e` → `验收`

---

## 5) 直接判定失败

- 没有可执行 E2E 用户故事，只有自然语言描述。
- 主链路已变更，但 E2E 断言/文档未同步。
- 宣称完成但缺命令、输出、产物路径三要素。
- 将最终交付门禁（`tc-acceptance-e2e`）误当开发过程门禁，导致过程失控。
