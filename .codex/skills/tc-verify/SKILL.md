---
name: tc-verify
description: Use when implementing refactors or behavior changes to enforce clean-architecture gates (no compatibility layers, no legacy leftovers, bounded complexity, and reproducible evidence) before delivery.
metadata:
  short-description: 统一质量门禁（禁兼容/禁遗留/禁堆债）
---

# tc-verify（统一质量门禁）

目标：在交付前确认“实现可跑 + 结构可维护 + 证据可复核”，默认拒绝兼容层、双轨逻辑和临时债常驻。

统一真源：
- `Doc Impact`、`交付三问`、`P/R` 自检、文档状态推进，以 `AGENTS.md` 的 DoD 为准。
- 工作流细节以 `docs/core/agent-workflow.md` 为准。

---

## 1) 何时必须触发

- 任意 `feat` / `fix` / `refactor` 的行为改动。
- 重构旧链路且准备宣称“完成/可交付”。
- `tc-debug` 修复后，需要确认未引入新债。

---

## 2) 执行顺序（固定）

1. 自动门禁（机器判定）
2. 结构复核（人工判定）
3. 证据归档（交付判定）

---

## 3) 自动门禁（必须先过）

```bash
bash scripts/quality_gate.sh
```

若需要追踪稳定性趋势（而不只看一次 pass/fail），可用 checkpoint 记录并输出 `pass@k / pass^k`：

```bash
python3 scripts/eval_checkpoint.py run --checkpoint quality-gate-main --command "bash scripts/quality_gate.sh"
python3 scripts/eval_checkpoint.py report --checkpoint quality-gate-main --k 1,3,5
```

常用变体：

```bash
bash scripts/quality_gate.sh --base main
bash scripts/quality_gate.sh --delete-list docs/plan/delete-list.txt
bash scripts/quality_gate.sh --fast
```

若本轮新增 factor，先做脚手架 dry-run：

```bash
python3 scripts/new_factor_scaffold.py --factor <name> --depends-on <dep1,dep2> --dry-run
```

---

## 4) 结构复核（交付说明必须回答）

- Delete Check：删了哪些旧路径/旧接口？
- No Dual Path：是否仍存在新旧双轨并行？
- Boundary Check：是否保持 `ingest -> store -> factor -> overlay -> read_model -> route` 单向流？
- Contract Check：`candle_id` 口径是否稳定一致？
- Rollback Check：最短回滚路径是否明确（`git revert <sha>` 或开关）？

---

## 5) 证据归档（最小模板）

```text
Gate:
- Command: bash scripts/quality_gate.sh --base main
- Output: <关键输出摘要>
- Artifacts: <output/...>

Design Check:
- Dual Path: no
- Boundary: pass
- Contract: pass

Doc Impact: yes/no
Rollback: git revert <sha>
```

---

## 6) 直接判定失败

- 自动门禁失败仍宣称完成。
- 为了兼容历史行为保留双轨逻辑。
- 交付缺少命令、关键输出或产物路径。
- 与 `AGENTS.md` DoD 冲突（例如漏写 `Doc Impact` / `交付三问`）。
