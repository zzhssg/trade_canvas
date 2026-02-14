---
name: tc-subagent-orchestration
description: Use when one task needs fan-out execution by multiple child Codex sessions with callback artifacts and a final aggregated report.
metadata:
  short-description: 子 session 编排（fan-out + callback + 汇总）
---

# tc-subagent-orchestration（子 session 编排）

目标：把“一个会话并行拆分多个子任务”落地成可执行流程，并保证可验收、可回滚、可追踪。

统一真源：
- 协作边界与门禁以 `AGENTS.md`、`docs/core/agent-workflow.md` 为准。
- 本 skill 只负责“并行编排 + 结果回收”，不替代 `tc-planning` / `tc-verify` / `tc-acceptance-e2e`。

---

## 1) 何时触发

- 一个任务可按目录/职责拆成 2+ 子任务，且子任务彼此低耦合。
- 需要“主会话统一下发、子会话并行执行、回调汇总”来提升吞吐。
- 需要标准化产物（每个子任务都有 events/log/result，便于追责和复盘）。

---

## 2) 何时不要用

- 单文件小改（串行更快）。
- 子任务对同一文件有高概率冲突（应先按目录所有权重切）。
- 关键技术决策未收敛（先走 `tc-planning` 问题包，再并行执行）。

---

## 3) 运行前约束（强制）

- 每个子任务必须明确：`id / prompt / cwd / 验收命令 / 回滚路径`。
- 子任务 prompt 必须写“允许改哪些目录，禁止改哪些目录”。
- 默认遵循目录所有权：`frontend/`、`backend/`、`docs/` 等边界不交叉。
- 汇总前禁止直接宣称完成，必须跑对应门禁（`pytest -q` / `npm run build` / `doc_audit`）。

---

## 4) 编排脚本（本仓）

统一脚本：`scripts/subagent_orchestrator.py`

### 4.1 生成 spec 模板

```bash
python3 scripts/subagent_orchestrator.py template \
  --output output/subagents/spec-example.json
```

### 4.2 执行 fan-out

```bash
python3 scripts/subagent_orchestrator.py run \
  --spec output/subagents/spec-example.json \
  --max-parallel 2
```

执行后会生成：
- `output/subagents/<run_id>/<task_id>/events.jsonl`
- `output/subagents/<run_id>/<task_id>/stderr.log`
- `output/subagents/<run_id>/<task_id>/last_message.txt`
- `output/subagents/<run_id>/<task_id>/result.json`
- `output/subagents/<run_id>/summary.json`
- `output/subagents/<run_id>/summary.md`

---

## 5) spec 最小格式

```json
{
  "run_name": "market-doc-and-tests",
  "max_parallel": 2,
  "defaults": {
    "cwd": ".",
    "timeout_sec": 1200
  },
  "tasks": [
    {
      "id": "docs-agent",
      "prompt": "仅更新 docs/core/agent-workflow.md 文档段落，不改业务代码。",
      "cwd": "."
    },
    {
      "id": "test-agent",
      "prompt": "运行 pytest -q 并总结失败点，不改代码。",
      "cwd": "."
    }
  ]
}
```

---

## 6) 回调与汇报约定

- 回调：脚本会在每个子任务结束时输出 `[callback] task=... status=...`。
- 汇总：读取 `summary.json`/`summary.md` 统一生成主会话交付说明。
- 交付必须包含：
  - 命令（完整）
  - 关键输出（成功数/失败数、失败任务 id）
  - 产物路径（`output/subagents/<run_id>/...`）

---

## 7) 风险与回滚

- 风险：并行写同一目录导致冲突、子任务 prompt 约束不清导致越界改动。
- 控制：
  - 先按目录所有权拆分；
  - prompt 明确“允许/禁止”路径；
  - 汇总前跑门禁并执行集成仲裁。
- 回滚：
  - 单子任务失败：按任务维度回滚（`git restore`/`git revert` 对应提交）；
  - 整体失败：回滚本轮 orchestrator 产物和相关改动。

---

## 8) 推荐串联

`tc-planning` → `tc-subagent-orchestration` → `tc-verify` → `tc-acceptance-e2e`（跨模块时）
